"""Prepare a reviewable integration patch without modifying the neighbouring AgentTrade checkout."""

import argparse
import ast
import difflib
from pathlib import Path

_OBSERVER = '''
_PROVIDER_OBSERVER: ContextVar[Any] = ContextVar("provider_observer", default=None)


@contextmanager
def observe_provider_calls(observer):
    """Bind a request/job observer; results stay in memory and observer failures are isolated."""
    token = _PROVIDER_OBSERVER.set(observer)
    try:
        yield
    finally:
        _PROVIDER_OBSERVER.reset(token)


def _notify_observer(provider, result, error, started):
    observer = _PROVIDER_OBSERVER.get()
    if observer is None:
        return
    try:
        observer(provider, result, error, (time.monotonic() - started) * 1000)
    except Exception:
        get_logger().warning("provider observer failed; business outcome preserved")

'''

_TEST = """import pytest

from agenttrade_sdk.provider_operations import meter_provider, observe_provider_calls


def test_observer_context_and_original_errors():
    rows = []
    with observe_provider_calls(lambda *args: rows.append(args)):
        assert meter_provider("fixture", lambda: "ok") == "ok"
        with observe_provider_calls(None):
            meter_provider("uncovered", lambda: "ok")
        with pytest.raises(ValueError, match="business"):
            meter_provider("fixture", lambda: (_ for _ in ()).throw(ValueError("business")))
    meter_provider("outside", lambda: "ok")
    assert len(rows) == 2
    assert rows[0][0:3] == ("fixture", "ok", None)
    assert isinstance(rows[1][2], ValueError)


def test_observer_outage_does_not_replace_business_outcome():
    def unavailable(*args):
        raise RuntimeError("observer unavailable")
    with observe_provider_calls(unavailable):
        assert meter_provider("fixture", lambda: 7) == 7
        with pytest.raises(ValueError, match="business"):
            meter_provider("fixture", lambda: (_ for _ in ()).throw(ValueError("business")))
"""


def replace_once(text, old, new):
    """Stop if the target drifted; never generate a partially matching integration."""
    if text.count(old) != 1:
        raise ValueError("Target code changed; review the integration anchors")
    return text.replace(old, new, 1)


def add_import(text, statement):
    """Insert after any module docstring and future imports."""
    nodes = ast.parse(text).body
    first = next(
        node
        for node in nodes
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        and not (isinstance(node, ast.ImportFrom) and node.module == "__future__")
    )
    lines = text.splitlines(keepends=True)
    lines.insert(first.lineno - 1, statement + "\n")
    return "".join(lines)


def prepare(root, destination):
    """Build a fixed-scope patch for the shared meter and authorised job entrypoints."""
    updated = {}
    path = "packages/py-sdk/src/agenttrade_sdk/provider_operations.py"
    text = (root / path).read_text()
    text = replace_once(text, "\ndef meter_provider(", _OBSERVER + "\ndef meter_provider(")
    text = replace_once(
        text,
        "        _record(provider, False, started, error)\n",
        "        _record(provider, False, started, error)\n"
        "        _notify_observer(provider, None, error, started)\n",
    )
    text = replace_once(
        text,
        "        return result\n    _record(provider, True, started, None)",
        "        _notify_observer(provider, result, None, started)\n"
        "        return result\n    _record(provider, True, started, None)",
    )
    text = replace_once(
        text,
        "    _record(provider, True, started, None)\n    return result",
        "    _record(provider, True, started, None)\n"
        "    _notify_observer(provider, result, None, started)\n    return result",
    )
    updated[path] = text
    here = Path(__file__).parent
    updated["packages/py-sdk/src/agenttrade_sdk/dispatcher_monitoring.py"] = (
        here / "dispatcher_monitoring.py"
    ).read_text()
    updated["packages/py-sdk/tests/test_provider_observer.py"] = _TEST
    for path, functions in {
        "services/advisor/app/domain/asset_compute.py": ["analyze_and_compute", "rescore_all"],
        "services/advisor/app/domain/slow_rescan.py": ["run_slow_rescan"],
        "services/advisor/app/domain/research_panel.py": ["answer_research_question"],
        "services/advisor/app/ingestion/refresh.py": ["run_refresh"],
    }.items():
        text = add_import(
            (root / path).read_text(),
            "from agenttrade_sdk.dispatcher_monitoring import monitor_job",
        )
        for name in functions:
            # Validate that a trusted organisation argument actually exists before wrapping.
            function = next(
                node
                for node in ast.parse(text).body
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
            arguments = [arg.arg for arg in function.args.args + function.args.kwonlyargs]
            if "organisation_id" not in arguments:
                raise ValueError(f"{name} has no verified organisation parameter")
            text = replace_once(text, f"\ndef {name}(", f'\n@monitor_job("{name}")\ndef {name}(')
        updated[path] = text
    path = "services/advisor/app/domain/asset_compute.py"
    updated[path] = updated[path].replace(
        "import monitor_job\n", "import monitor_job, submit_context\n"
    )
    updated[path] = replace_once(
        updated[path],
        "executor.submit(compute, component)",
        "submit_context(executor, compute, component)",
    )
    path = "services/advisor/app/adapters/llm_tool_loop.py"
    text = add_import(
        (root / path).read_text(), "from agenttrade_sdk.dispatcher_monitoring import submit_context"
    )
    start = text.index("        return list(\n            pool.map(", text.index("def run_panel("))
    text = (
        text[:start]
        + """        futures = [
            submit_context(
                pool, run_tool_loop, provider, system=system, user_prompt=user_prompt,
                context_json=context_json, tools=tools, max_rounds=max_rounds,
            )
            for provider in providers
        ]
        return [future.result() for future in futures]
"""
    )
    updated[path] = text
    path = "services/advisor/app/domain/scheduler_tasks.py"
    text = add_import(
        (root / path).read_text(), "from agenttrade_sdk.dispatcher_monitoring import monitor_scope"
    )
    text = replace_once(
        text,
        "        with automatic_refresh(), track_anthropic_usage() as usage, "
        "track_provider_calls() as calls:",
        "        with (\n"
        "            monitor_scope(task.get('organisation_id'), job_name=str(task['name'])),\n"
        "            automatic_refresh(), track_anthropic_usage() as usage, "
        "track_provider_calls() as calls,\n"
        "        ):",
    )
    updated[path] = text
    chunks = []
    for path, after in updated.items():
        ast.parse(after)
        before = (root / path).read_text() if (root / path).exists() else ""
        chunks.extend(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile="a/" + path if before else "/dev/null",
                tofile="b/" + path,
            )
        )
    destination.write_text("".join(chunks))
    print(f"Prepared {len(updated)} files for review: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.target, args.output)

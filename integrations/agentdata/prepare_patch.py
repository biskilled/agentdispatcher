"""Prepare a minimal patch against the actual AgentData shared completion/prompt entry points."""

# Exact source anchors retain AgentData's existing line lengths.
# ruff: noqa: E501

import argparse
import difflib
from pathlib import Path


def replace_once(text, old, new):
    """Refuse source drift so applying the integration cannot silently miss a call path."""
    if text.count(old) != 1:
        raise ValueError("AgentData source changed; review the bridge anchors before patching")
    return text.replace(old, new, 1)


def prepare(root):
    """Return reviewable changes without modifying the AgentData checkout."""
    llm_path = "backend/core/llm.py"
    original = (root / llm_path).read_text()
    updated = replace_once(
        original,
        '        return fn(system, user, model, max_tokens, **({"images":images} if images else {}))',
        "        from core.dispatcher_monitoring import complete as monitored_complete\n"
        "        return monitored_complete(fn, provider, system, user, model, max_tokens,\n"
        '                                  **({"images":images} if images else {}))',
    )
    updated = replace_once(
        updated,
        '    with httpx.Client(timeout=_call_timeout.get() or settings.timeout("llm", 120)) as client:',
        "    from core.dispatcher_monitoring import gateway_metadata\n"
        "    if context := gateway_metadata():\n"
        '        body["metadata"] = {"dispatcher_context": context}\n'
        '    with httpx.Client(timeout=_call_timeout.get() or settings.timeout("llm", 120)) as client:',
    )
    prompt_path = "backend/core/prompt_loader.py"
    prompt = (root / prompt_path).read_text()
    old = """            text, in_tok, out_tok = complete(
                system=cfg.system, user=user, model=model_id,
                max_tokens=max_tokens or cfg.max_tokens, **({'schema':schema} if schema else {}))"""
    new = """            from core.dispatcher_monitoring import prompt_context
            with prompt_context(key, cfg, model=model_id, max_tokens=max_tokens or cfg.max_tokens):
                text, in_tok, out_tok = complete(
                    system=cfg.system, user=user, model=model_id,
                    max_tokens=max_tokens or cfg.max_tokens, **({'schema':schema} if schema else {}))"""
    return {
        llm_path: (original, updated),
        prompt_path: (prompt, replace_once(prompt, old, new)),
        "backend/core/dispatcher_monitoring.py": (
            "",
            Path(__file__).with_name("dispatcher_monitoring.py").read_text(),
        ),
    }


def main():
    """Write a reviewable patch without touching the app checkout or configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentdata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    changes = prepare(args.agentdata)
    args.output.write_text(
        "".join(
            "".join(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile="a/" + path if before else "/dev/null",
                    tofile="b/" + path,
                )
            )
            for path, (before, after) in changes.items()
        )
    )
    print("Prepared AgentData gateway integration patch; source checkout unchanged.")


if __name__ == "__main__":
    main()

"""MCP observation without a dependency on a particular MCP SDK version."""

import time
from uuid import UUID, uuid4

CONTEXT_KEY = "agentdispatcher/context"
_CONTEXT = frozenset(
    {
        "project",
        "work_item",
        "pipeline_role",
        "session_id",
        "trace_id",
        "job_run_id",
        "config_version",
    }
)


def request_context(meta):
    """Read bounded attribution only; MCP metadata never grants identity or tenant access."""
    values = (meta or {}).get(CONTEXT_KEY, {})
    if not isinstance(values, dict):
        return {}
    context = {
        name: value
        for name, value in values.items()
        if name in _CONTEXT and isinstance(value, str) and 0 < len(value) <= 100
    }
    if "job_run_id" in context:
        try:
            context["job_run_id"] = str(UUID(context["job_run_id"]))
        except ValueError:
            del context["job_run_id"]
    return context


async def call_tool(monitor, client, server_id, name, arguments=None, *, meta=None, **billing):
    """Observe one MCP invocation and forward context for instrumented nested calls."""
    context = {**request_context(meta), **monitor.export_context()}
    context.setdefault("trace_id", uuid4().hex)
    started = time.perf_counter()
    status = "error"
    with monitor.context(**context):
        try:
            result = await client.call_tool(name, arguments, meta={CONTEXT_KEY: context})
            status = "error" if result.is_error else "success"
            return result
        finally:
            monitor.record(
                provider=server_id,
                operation=name,
                resource_kind="tool",
                status=status,
                duration_ms=(time.perf_counter() - started) * 1000,
                source="mcp-connector",
                **billing,
            )

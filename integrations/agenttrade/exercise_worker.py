"""Separate queue worker with a real MCP client/server boundary and synthetic LLM responses."""

import asyncio
import json
import sys

from agentdispatcher_sdk.mcp import call_tool, request_context
from agentdispatcher_sdk.registry import MonitorRegistry
from mcp import Client
from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool


async def execute(message, registry):
    """Resolve credentials from the worker environment; queue metadata carries no authority."""
    with registry.scope(message["organisation"], **message["context"]) as monitor:
        assert monitor is not None

        async def list_tools(ctx, params):
            return ListToolsResult(tools=[Tool(name="analysis", input_schema={"type": "object"})])

        async def invoke(ctx, params):
            with monitor.context(**request_context(params.meta)):
                for _ in range(2):
                    monitor.record(
                        provider="fixture-llm",
                        operation="completion",
                        resource_kind="llm",
                        source="mcp-worker",
                        status="success",
                        status_code=200,
                        duration_ms=1,
                        model="fixture-model",
                        input_tokens=7,
                        output_tokens=3,
                        api_id="fixture-llm",
                    )
            return CallToolResult(
                content=[TextContent(type="text", text="Synthetic private result")]
            )

        server = Server("fixture-analysis", on_list_tools=list_tools, on_call_tool=invoke)
        async with Client(server) as client:
            result = await call_tool(
                monitor, client, "fixture-mcp", "analysis", api_id="fixture-tool"
            )
            assert not result.is_error
            assert result.content[0].text == "Synthetic private result"


def main():
    """Consume one serialized fixture job and prove context survives worker and MCP boundaries."""
    message = json.load(sys.stdin)
    assert set(message) == {"organisation", "context"}
    assert not {"tenant_id", "key", "secret", "token"}.intersection(message["context"])
    registry = MonitorRegistry.from_environment("AGENTTRADE_DISPATCHER_BINDINGS")
    try:
        asyncio.run(execute(message, registry))
    finally:
        counters = registry.close()
        assert all(
            row["flushed"] and not row["failed"] and not row["dropped"] for row in counters.values()
        )
    print("Queue worker and MCP boundary verified.")


if __name__ == "__main__":
    main()

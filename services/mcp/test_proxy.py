"""Real MCP protocol fixture, using the same bounded exporter as application SDKs."""

import json
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

import httpx
from agentdispatcher_sdk import Monitor
from agentdispatcher_sdk.mcp import request_context
from mcp import Client
from mcp.server import MCPServer
from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
from proxy import Registration, create_proxy


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    """Tool charges and nested provider charges remain distinct, with one shared trace."""

    async def test_nested_calls_schema_failures_and_private_payloads(self):
        events = []

        def collect(request):
            self.assertEqual(request.headers["Authorization"], "Bearer fixture-sdk-secret")
            events.extend(json.loads(request.content)["events"])
            return httpx.Response(202, json={"accepted": 1})

        monitor = Monitor(
            "https://dispatcher.fixture.test",
            "fixture-sdk-secret",
            "research",
            "test",
            transport=httpx.MockTransport(collect),
        )
        private = "private upstream argument and result"

        async def tools(ctx, params):
            return ListToolsResult(
                tools=[
                    Tool(
                        name="research",
                        input_schema={
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    ),
                    Tool(name="fails", input_schema={"type": "object"}),
                    Tool(name="restricted", input_schema={"type": "object"}),
                ]
            )

        async def invoke(ctx, params):
            if params.name == "fails":
                return CallToolResult(
                    is_error=True,
                    content=[TextContent(type="text", text="upstream rejected request")],
                )
            self.assertEqual(params.arguments["query"], private)
            self.assertNotIn("secret", params.meta)
            with monitor.context(**request_context(params.meta)):
                for cost in ("0.04", "0.06"):
                    monitor.record(
                        provider="fixture-llm",
                        operation="chat",
                        resource_kind="llm",
                        status="success",
                        duration_ms=1,
                        reported_cost=cost,
                        reported_currency="USD",
                    )
            return CallToolResult(
                content=[TextContent(type="text", text=private)],
                structured_content={"answer": private},
            )

        upstream = Server("fixture", on_list_tools=tools, on_call_tool=invoke)
        registration = Registration(
            server_id="research-server",
            app="research",
            environment="test",
            command="unused",
            allowed_tools=["research", "fails"],
        )
        try:
            async with Client(upstream) as connection:
                async with Client(create_proxy(registration, connection, monitor)) as client:
                    self.assertEqual(
                        {tool.name for tool in (await client.list_tools()).tools},
                        {"research", "fails"},
                    )
                    result = await client.call_tool(
                        "research",
                        {"query": private},
                        meta={
                            "secret": "must-not-forward",
                            "agentdispatcher/context": {
                                "session_id": "session-1",
                                "tenant_id": "spoofed",
                            },
                        },
                    )
                    self.assertFalse(result.is_error, result)
                    self.assertEqual(result.structured_content["answer"], private)
                    self.assertTrue((await client.call_tool("fails")).is_error)
                    self.assertTrue((await client.call_tool("restricted")).is_error)
        finally:
            self.assertTrue(monitor.close())
        self.assertEqual(len(events), 4)
        self.assertNotIn(private, json.dumps(events))
        llm = [row for row in events if row["resource_kind"] == "llm"]
        tool = next(row for row in events if row["operation"] == "research")
        self.assertEqual(sum(Decimal(row["reported_cost"]) for row in llm), Decimal("0.10"))
        self.assertNotIn("reported_cost", tool)
        self.assertEqual({row["trace_id"] for row in llm}, {tool["trace_id"]})
        self.assertEqual(tool["session_id"], "session-1")
        self.assertNotIn("tenant_id", tool)
        self.assertEqual(
            next(row for row in events if row["operation"] == "fails")["status"], "error"
        )

    async def test_export_failure_does_not_fail_tool(self):
        def unavailable(request):
            return httpx.Response(503)

        monitor = Monitor(
            "https://dispatcher.fixture.test",
            "test",
            "a",
            "test",
            attempts=1,
            transport=httpx.MockTransport(unavailable),
        )
        server = MCPServer("fixture")

        @server.tool()
        def answer() -> str:
            """Return a business result when monitoring is unavailable."""
            return "result"

        registration = Registration(
            server_id="fixture", app="a", environment="test", command="unused"
        )
        try:
            async with Client(server) as upstream:
                async with Client(create_proxy(registration, upstream, monitor)) as client:
                    self.assertFalse((await client.call_tool("answer")).is_error)
        finally:
            monitor.close()
        self.assertEqual(monitor.failed, 1)

    def test_explicit_upstream_secret_boundary(self):
        registration = Registration(
            server_id="fixture",
            app="a",
            environment="test",
            command="fixture",
            upstream_env={"API_KEY": "UPSTREAM_API_KEY"},
        )
        with patch.dict(
            os.environ,
            {"UPSTREAM_API_KEY": "upstream-only", "DISPATCHER_SDK_KEY": "telemetry-only"},
        ):
            self.assertEqual(registration.upstream().env, {"API_KEY": "upstream-only"})
            registration.upstream_env = {"API_KEY": "DISPATCHER_SDK_KEY"}
            with self.assertRaises(ValueError):
                registration.upstream()
        with self.assertRaises(ValueError):
            Registration(
                server_id="fixture", app="a", environment="test", command="fixture", version=2
            )


if __name__ == "__main__":
    unittest.main()

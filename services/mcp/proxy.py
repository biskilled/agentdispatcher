"""Local, tools-only MCP connector with separate upstream and telemetry credentials."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from agentdispatcher_sdk import Monitor
from agentdispatcher_sdk.mcp import call_tool
from mcp import Client, StdioServerParameters
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, field_validator
from server import Settings


class Registration(BaseModel):
    """Operator-owned registration; neither models nor incoming MCP metadata can change it."""

    model_config = ConfigDict(extra="forbid")
    version: int = 1
    server_id: str = Field(min_length=1, max_length=100)
    app: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=50)
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    upstream_env: dict[str, str] = Field(default_factory=dict)
    api_id: str | None = Field(default=None, max_length=100)
    connection_id: str | None = Field(default=None, max_length=100)
    allowed_tools: list[str] | None = None

    @field_validator("version")
    @classmethod
    def supported_version(cls, value):
        """Reject unknown contracts instead of guessing field semantics."""
        if value != 1:
            raise ValueError("Unsupported MCP registration version")
        return value

    def upstream(self):
        """Resolve explicit environment names; never inherit the connector's SDK credential."""
        if "DISPATCHER_SDK_KEY" in self.upstream_env.values():
            raise ValueError("Use a separate upstream service credential")
        return StdioServerParameters(
            command=self.command,
            args=self.args,
            env={name: os.environ[source] for name, source in self.upstream_env.items()},
        )


def create_proxy(registration, upstream, monitor):
    """Forward schemas/results unchanged and observe only authorized tool invocations."""
    allowed = set(registration.allowed_tools) if registration.allowed_tools is not None else None

    async def list_tools(ctx, params):
        result = await upstream.list_tools(cursor=params.cursor if params else None)
        if allowed is not None:
            result = result.model_copy(
                update={"tools": [tool for tool in result.tools if tool.name in allowed]}
            )
        return result

    async def invoke(ctx, params):
        if allowed is not None and params.name not in allowed:
            return rejected("Tool is not authorized by this connector registration")
        billing = {
            name: value
            for name in ("api_id", "connection_id")
            if (value := getattr(registration, name)) is not None
        }
        try:
            return await call_tool(
                monitor,
                upstream,
                registration.server_id,
                params.name,
                params.arguments,
                meta=params.meta,
                **billing,
            )
        except Exception:
            # Upstream exception text can contain credentials or argument values.
            logging.warning("Registered MCP upstream call failed")
            return rejected("Registered MCP upstream is unavailable or rejected this call")

    return Server(
        "AgentDispatcher connector", version="0.1.0", on_list_tools=list_tools, on_call_tool=invoke
    )


def rejected(message):
    """Return an explicit tool error without exposing upstream exception details."""
    return CallToolResult(is_error=True, content=[TextContent(type="text", text=message)])


async def run(registration, settings):
    """Run one locally authorized upstream; telemetry failures do not fail business tools."""
    upstream = registration.upstream()
    monitor = Monitor(
        settings.api_url,
        os.environ["DISPATCHER_SDK_KEY"],
        registration.app,
        registration.environment,
        timeout=settings.timeout,
    )
    try:
        async with Client(
            upstream,
            read_timeout_seconds=float(os.environ.get("DISPATCHER_MCP_TOOL_TIMEOUT", "120")),
        ) as client:
            proxy = create_proxy(registration, client, monitor)
            async with stdio_server() as (reader, writer):
                await proxy.run(reader, writer, proxy.create_initialization_options())
    finally:
        drained = await asyncio.to_thread(monitor.close)
        if not drained or monitor.failed or monitor.dropped:
            logging.warning(
                "MCP telemetry incomplete: failed=%s dropped=%s drained=%s",
                monitor.failed,
                monitor.dropped,
                drained,
            )


def main():
    """Load a local registration path; configuration contains env names, never secret values."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    registration = Registration.model_validate(json.loads(args.config.read_text()))
    asyncio.run(run(registration, Settings.from_env()))


if __name__ == "__main__":
    main()

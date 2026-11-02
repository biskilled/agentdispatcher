"""The protocol-independent MCP helper persists valid charges through SDK/API/PostgreSQL."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from agentdispatcher_sdk.mcp import call_tool, request_context
from test_observations import monitor_fixture


def test_mcp_nested_provider_costs_and_explicit_tool_price(system):
    plan = {
        "api_id": "research-tools",
        "name": "Tool execution fee",
        "pricing": "per_unit",
        "effective_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "unit_price": "0.02",
        "charge_outcomes": ["success"],
        "currency": "USD",
    }
    response = system["client"].post("/api/plans", json=plan)
    assert response.status_code == 201, response.text
    monitor = monitor_fixture(system)

    class OwnedServer:
        async def call_tool(self, name, arguments, meta):
            """A server instruments provider calls and imports bounded per-call attribution."""
            with monitor.context(**request_context(meta)):
                for amount in ("0.04", "0.06"):
                    monitor.record(
                        provider="llm",
                        operation="chat",
                        resource_kind="llm",
                        status="success",
                        duration_ms=1,
                        reported_cost=amount,
                        reported_currency="USD",
                    )
            return SimpleNamespace(is_error=False, answer="private result")

    result = asyncio.run(
        call_tool(
            monitor,
            OwnedServer(),
            "research",
            "lookup",
            {"query": "private query"},
            meta={
                "agentdispatcher/context": {
                    "session_id": "mcp-session",
                    "job_run_id": "invalid",
                    "tenant_id": "spoof",
                }
            },
            api_id="research-tools",
        )
    )
    assert result.answer == "private result"
    assert monitor.close() and monitor.failed == 0
    overview = system["client"].get("/api/overview").json()
    assert overview["counts"]["attempts"] == 3
    assert sum(Decimal(row["cost"]) for row in overview["totals"]) == Decimal("0.12")
    rows = system["client"].get("/api/events").json()
    assert "private" not in str(rows)
    assert len({row["payload"]["trace_id"] for row in rows}) == 1
    assert {row["payload"]["session_id"] for row in rows} == {"mcp-session"}

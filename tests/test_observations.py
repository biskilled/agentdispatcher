"""Overlapping observers retain metadata while only canonical physical attempts consume costs."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from agentdispatcher_sdk import Monitor
from agentdispatcher_sdk.http import MonitoredTransport
from agentdispatcher_sdk.providers import ProviderObserver
from test_access import invite_user
from test_integration import event, ingest

_SQL_REFERENCES = "SELECT event_id FROM mem_observations"


def monitor_fixture(system):
    """Send the real SDK queue through real API authentication into PostgreSQL."""

    def receive(request):
        response = system["client"].post(
            request.url.path,
            json=json.loads(request.content),
            headers={"Authorization": request.headers["Authorization"]},
        )
        return httpx.Response(response.status_code, json=response.json())

    return Monitor(
        "http://testserver",
        system["key"]["secret"],
        "trader",
        "test",
        transport=httpx.MockTransport(receive),
        retry_delay=0,
    )


def test_sdk_gateway_overlap_retains_retries_and_never_adds_client_cost(system):
    monitor = monitor_fixture(system)
    calls = []

    def provider(request):
        calls.append(request)
        return httpx.Response(
            429 if len(calls) == 1 else 200,
            json={"model": "model-a", "usage": {"prompt_tokens": 4}},
        )

    transport = MonitoredTransport(
        monitor,
        httpx.MockTransport(provider),
        provider="proxy",
        api_id="llm",
        operation="completion",
    )
    observer = ProviderObserver(monitor, {"proxy": {"resource_kind": "llm", "api_id": "llm"}})
    with monitor.job("Mixed usage fixture"):
        monitor.record(
            provider="market",
            operation="read",
            resource_kind="api",
            status="success",
            duration_ms=1,
            reported_cost="0.04",
            reported_currency="USD",
        )
        with monitor.gateway() as context:
            with httpx.Client(transport=transport) as client:
                for _ in range(2):
                    response = client.post(
                        "https://gateway.fixture.test/completions",
                        json={"metadata": {"dispatcher_context": context}},
                    )
                    observer("proxy", response, None, 1)
    assert monitor.close() and monitor.failed == 0
    coverage = system["client"].get("/api/coverage").json()
    assert sum(row["missing"] for row in coverage["references"]) == 4
    assert system["client"].get("/api/overview").json()["counts"]["attempts"] == 1
    upstream = [
        event(
            source="litellm",
            operation_id=context["operation_id"],
            status=status,
            reported_cost=cost,
            reported_currency="USD",
        )
        for status, cost in (("error", "0.1"), ("success", "0.2"))
    ]
    assert ingest(system, upstream).status_code == 202
    assert ingest(system, upstream).json()["duplicates"] == 2
    summary = system["client"].get("/api/overview").json()
    assert summary["counts"]["attempts"] == 3
    assert sum(Decimal(row["cost"]) for row in summary["totals"]) == Decimal("0.34")
    assert not system["client"].get("/api/coverage").json()["gaps"]


def test_transport_and_provider_share_physical_attempt_including_failures(system):
    plan = {
        "api_id": "llm",
        "name": "Synthetic token fixture",
        "pricing": "per_token",
        "effective_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "input_token_price": "0.001",
        "output_token_price": "0.002",
        "currency": "USD",
    }
    assert system["client"].post("/api/plans", json=plan).status_code == 201
    monitor = monitor_fixture(system)
    observer = ProviderObserver(monitor, {"provider": {"resource_kind": "llm", "api_id": "llm"}})

    def provider(request):
        if request.method == "GET":
            raise httpx.ReadTimeout("secret URL must never be exported", request=request)
        return httpx.Response(
            200,
            json={
                "model": "model-a",
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                "choices": [{"message": {"content": "private"}}],
            },
        )

    transport = MonitoredTransport(
        monitor,
        httpx.MockTransport(provider),
        provider="provider",
        api_id="llm",
        operation="completion",
        canonical_source="provider-observer",
    )
    with httpx.Client(transport=transport) as client:
        response = client.post("https://provider.fixture.test/private?key=secret")
        observer("provider", response, None, 1)
        try:
            client.get("https://provider.fixture.test/private")
        except httpx.ReadTimeout as error:
            observer("provider", None, error, 2)
    assert monitor.close() and monitor.failed == 0
    events = system["client"].get("/api/events").json()
    assert len(events) == 2 and {row["status"] for row in events} == {"success", "timeout"}
    assert next(row for row in events if row["status"] == "success")["cost"] == "0.008"
    assert "private" not in str(events) and "secret URL" not in str(events)
    coverage = system["client"].get("/api/coverage").json()
    assert len(coverage["references"]) == 1 and coverage["references"][0]["matched"] == 2


def test_reference_replay_scope_and_permissions_do_not_create_charges(system):
    client = system["client"]
    row = event(source="otel", reported_cost="999", reported_currency="USD")
    body = {"observations": [{"event": row, "expected_source": "fixture"}]}
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    assert client.post("/api/observations", json=body, headers=headers).json()["inserted"] == 1
    assert client.post("/api/observations", json=body, headers=headers).json()["duplicates"] == 1
    assert client.get("/api/overview").json()["counts"]["attempts"] == 0
    altered = {"observations": [{**body["observations"][0], "expected_source": "changed"}]}
    assert client.post("/api/observations", json=altered, headers=headers).status_code == 409
    foreign = {
        "observations": [
            {
                "event": {**row, "event_id": str(uuid4()), "app": "foreign"},
                "expected_source": "fixture",
            }
        ]
    }
    assert client.post("/api/observations", json=foreign, headers=headers).status_code == 403
    assert (
        ingest(
            system, [event(attempt_id=row["attempt_id"], operation_id=row["operation_id"])]
        ).status_code
        == 202
    )
    assert not client.get("/api/coverage").json()["gaps"]
    with system["db"].tenant(system["other"].tenant_id) as connection:
        assert not connection.execute(_SQL_REFERENCES).fetchall()
    session, _, _ = invite_user(system, "member")
    client.cookies.set("dispatcher_session", session)
    assert not client.get("/api/coverage").json()["references"]
    system["auth"].revoke_key(system["owner"], system["key"]["id"])
    assert client.post("/api/observations", json=body, headers=headers).status_code == 401


def test_http_unknown_exception_cannot_replace_business_failure():
    """Exceptions that reject custom attributes retain their original business outcome."""

    class FrozenError(Exception):
        def __setattr__(self, name, value):
            if name == "dispatcher_correlation":
                raise AttributeError("custom attributes are disabled")
            super().__setattr__(name, value)

    monitor = Monitor(
        "http://testserver",
        "fixture",
        "app",
        "test",
        transport=httpx.MockTransport(lambda _: httpx.Response(202)),
    )

    def fail(request):
        raise FrozenError("business failure")

    transport = MonitoredTransport(
        monitor, httpx.MockTransport(fail), provider="fixture", api_id="api", operation="read"
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(FrozenError, match="business failure"):
            client.get("https://fixture.test")
    assert monitor.close()

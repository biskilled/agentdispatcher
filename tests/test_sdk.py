"""Export resilience and asynchronous job attribution without external providers."""

import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from agentdispatcher_sdk import Monitor


def test_retries_preserve_id_and_jobs_stay_separate():
    received = []

    def receive(request):
        received.append((request.url.path, json.loads(request.content)))
        return httpx.Response(503 if len(received) == 1 else 202)

    monitor = Monitor(
        "http://testserver",
        "fixture-only",
        "trader",
        "test",
        transport=httpx.MockTransport(receive),
        retry_delay=0,
    )

    def run(name):
        with monitor.job(name):
            with monitor.operation(provider="synthetic", operation="get") as measured:
                measured["status_code"] = 200

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(run, ["first", "second"]))
    assert monitor.close()
    assert received[0] == received[1]
    usage = [data["events"][0] for path, data in received if path == "/api/ingest"]
    assert len({item["job_run_id"] for item in usage}) == 2
    assert monitor.failed == 0


def test_business_error_preserved_and_export_failures_visible():
    monitor = Monitor(
        "http://testserver",
        "fixture-only",
        "trader",
        "test",
        attempts=1,
        transport=httpx.MockTransport(lambda _: httpx.Response(401)),
    )
    with pytest.raises(ValueError, match="business error"):
        with monitor.job("fails"):
            with monitor.operation(provider="synthetic", operation="get"):
                raise ValueError("business error")
    assert monitor.close()
    assert monitor.failed == 3
    monitor.record(
        provider="synthetic", operation="get", resource_kind="api", status="success", duration_ms=1
    )
    assert monitor.dropped == 1


def test_reported_success_cannot_hide_business_failure():
    received = []

    def receive(request):
        received.append(json.loads(request.content))
        return httpx.Response(202)

    monitor = Monitor(
        "http://testserver",
        "fixture-only",
        "trader",
        "test",
        transport=httpx.MockTransport(receive),
    )
    with pytest.raises(ValueError):
        with monitor.operation(provider="synthetic", operation="get") as measured:
            measured["status"] = "success"
            raise ValueError("failed after receiving response")
    assert monitor.close()
    assert received[0]["events"][0]["status"] == "error"


def test_http_attempts_context_and_delegation_never_persist_credentials():
    from agentdispatcher_sdk.http import MonitoredTransport

    received = []

    def receive(request):
        received.append((dict(request.headers), json.loads(request.content)))
        return httpx.Response(202)

    monitor = Monitor(
        "http://testserver", "fixture-key", "trader", "test", transport=httpx.MockTransport(receive)
    )
    transport = MonitoredTransport(
        monitor,
        httpx.MockTransport(lambda _: httpx.Response(429)),
        provider="market",
        api_id="market",
        operation="prices/{asset}",
    )
    with monitor.context(project="trade", work_item="TA1"):
        with monitor.user("short-lived-consent"):
            with httpx.Client(transport=transport) as client:
                assert (
                    client.get("https://fixture.test/prices/secret?api_key=private").status_code
                    == 429
                )
            assert monitor.export_context() == {"project": "trade", "work_item": "TA1"}
    monitor.record(
        provider="market", operation="later", resource_kind="api", status="success", duration_ms=0
    )
    assert monitor.close()
    headers, data = received[0]
    assert headers["x-user-delegation"] == "short-lived-consent"
    assert "short-lived-consent" not in str(data)
    assert "private" not in str(data) and "secret" not in str(data)
    assert data["events"][0]["status"] == "error"
    assert data["events"][0]["work_item"] == "TA1"
    assert "x-user-delegation" not in received[1][0]
    assert "work_item" not in received[1][1]["events"][0]

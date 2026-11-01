"""Shared client observations stay tenant scoped, metadata only and exporter-failure isolated."""

import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from agentdispatcher_sdk import Monitor
from agentdispatcher_sdk.registry import MonitorRegistry


def test_registry_keys_context_tokens_failures_and_unmapped_scope(monkeypatch):
    received = []

    def receive(request):
        received.append(
            (request.headers["Authorization"], request.url.path, json.loads(request.content))
        )
        return httpx.Response(202)

    def factory(**kwargs):
        return Monitor(**kwargs, transport=httpx.MockTransport(receive))

    monkeypatch.setenv("FIXTURE_ENDPOINT", "https://fixture.example.test")
    monkeypatch.setenv("FIXTURE_A", "fixture-a")
    monkeypatch.setenv("FIXTURE_B", "fixture-b")
    monkeypatch.setenv("FIXTURE_CONFIG", "fixture-config-version")
    bindings = {
        tenant: {
            "endpoint_env": "FIXTURE_ENDPOINT",
            "key_env": key,
            "app": "trader",
            "environment": "test",
            "providers": {"llm": {"resource_kind": "llm"}},
            "context": {"project": "fixture"},
            "config_version_env": "FIXTURE_CONFIG",
        }
        for tenant, key in (("a", "FIXTURE_A"), ("b", "FIXTURE_B"))
    }
    registry = MonitorRegistry(bindings, factory)

    def run(tenant):
        with registry.scope(tenant, job_name="scheduled-fixture") as monitor:
            observer = registry.observer(tenant, monitor)
            response = httpx.Response(
                200,
                json={
                    "model": "fixture-model",
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                    "content": "DO NOT EXPORT",
                },
            )
            observer("llm", response, None, 3)
            with registry.scope(tenant, job_name="nested") as same:
                assert same is monitor
                observer("llm", None, httpx.ReadTimeout("DO NOT EXPORT"), 5)
            with registry.scope("unknown") as missing:
                assert missing is None

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(run, ["a", "b"]))
    assert all(row["flushed"] for row in registry.close().values())
    assert registry.unmapped_scopes == 2
    assert "DO NOT EXPORT" not in str(received)
    for key in ("Bearer fixture-a", "Bearer fixture-b"):
        rows = [
            body
            for credential, path, body in received
            if credential == key and path == "/api/ingest"
        ]
        assert len(rows) == 2
        assert rows[0]["events"][0]["input_tokens"] == 7
        assert rows[1]["events"][0]["status"] == "timeout"
        assert all(row["events"][0]["config_version"] == "fixture-config-version" for row in rows)
        jobs = [
            body
            for credential, path, body in received
            if credential == key and path == "/api/jobs/events"
        ]
        assert len(jobs) == 2
        assert {job["state"] for job in jobs} == {"running", "completed"}


def test_registry_invalid_and_missing_config_remain_visible(monkeypatch):
    with pytest.raises(ValueError):
        MonitorRegistry({"a": {"key_env": "MISSING"}})
    registry = MonitorRegistry(
        {
            "a": {
                "endpoint_env": "UNSET_ENDPOINT",
                "key_env": "UNSET_KEY",
                "app": "trader",
                "environment": "test",
            }
        }
    )
    with registry.scope("a", job_name="business") as monitor:
        assert monitor is None
    assert registry.setup_failures == 1


def test_manual_wrapper_and_http_hook_keep_only_distinct_retry_attempts():
    from agentdispatcher_sdk.http import MonitoredTransport

    events = []

    def exported(request):
        events.extend(json.loads(request.content)["events"])
        return httpx.Response(202)

    monitor = Monitor(
        "https://fixture.example.test",
        "fixture",
        "trader",
        "test",
        transport=httpx.MockTransport(exported),
    )
    replies = iter([429, 200])
    transport = MonitoredTransport(
        monitor,
        httpx.MockTransport(lambda request: httpx.Response(next(replies))),
        provider="fixture",
        api_id="market",
        operation="price",
    )
    with httpx.Client(transport=transport) as client:
        with monitor.operation(provider="fixture", operation="price", api_id="market"):
            assert client.get("https://fixture.example.test/price").status_code == 429
            assert client.get("https://fixture.example.test/price").status_code == 200
    assert monitor.close()
    assert len(events) == 2
    assert len({event["attempt_id"] for event in events}) == 2
    assert len({event["operation_id"] for event in events}) == 1
    assert [event["status"] for event in events] == ["error", "success"]

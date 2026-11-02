"""Authenticated OTLP traces use the same ledger and never store messages or arbitrary spans."""

import copy
import time
from decimal import Decimal
from uuid import uuid4

from test_integration import event, ingest


def attribute(key, value):
    """Encode the OTLP JSON scalar representation used by actual collectors."""
    kind = (
        "boolValue" if type(value) is bool else "intValue" if type(value) is int else "stringValue"
    )
    return {"key": key, "value": {kind: str(value) if kind == "intValue" else value}}


def span(**attributes):
    """Build one synthetic physical inference span with body content that must be discarded."""
    start = time.time_ns()
    values = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "fixture-provider",
        "gen_ai.request.model": "model-a",
        "gen_ai.usage.input_tokens": 4,
        "gen_ai.usage.output_tokens": 2,
        "dispatcher.cost": "0.06",
        "dispatcher.currency": "USD",
        "gen_ai.input.messages": "private prompt",
        **attributes,
    }
    return {
        "traceId": uuid4().hex,
        "spanId": uuid4().hex[:16],
        "name": "private user content",
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(start + 1_000_000),
        "attributes": [attribute(key, value) for key, value in values.items()],
        "events": [{"name": "private exception", "attributes": []}],
    }


def export_body(spans, app="trader", **attributes):
    """Represent OTEL_RESOURCE_ATTRIBUTES separately from per-request attributes."""
    values = {"service.name": app, "deployment.environment.name": "test", **attributes}
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [attribute(key, value) for key, value in values.items()]
                },
                "scopeSpans": [{"scope": {"name": "fixture"}, "spans": spans}],
            }
        ]
    }


def send(system, body, **kwargs):
    """Use normal SDK key authentication, not a privileged collector bypass."""
    return system["client"].post(
        "/api/otlp/v1/traces",
        json=body,
        headers={"Authorization": "Bearer " + system["key"]["secret"]},
        **kwargs,
    )


def test_otlp_partial_success_idempotency_context_and_privacy(system):
    first = span(**{"agentdesk.work_item": "TA-two"})
    bad = span(**{"gen_ai.operation.name": "invoke_agent"})
    body = export_body(
        [first, bad], **{"agentdesk.project": "trade", "agentdesk.work_item": "TA-one"}
    )
    response = send(system, body)
    assert response.status_code == 200, response.text
    assert response.json()["partialSuccess"]["rejectedSpans"] == "1"
    assert send(system, body).status_code == 200
    events = system["client"].get("/api/events").json()
    assert len(events) == 1
    assert events[0]["payload"]["work_item"] == "TA-two"
    assert events[0]["payload"]["project"] == "trade"
    assert events[0]["cost_kind"] == "app_estimate" and events[0]["cost"] == "0.06"
    assert events[0]["payload"]["duration_ms"] == "1"
    assert "private" not in str(events)
    adapters = system["client"].get("/api/coverage").json()["adapters"]
    assert adapters[0]["accepted_exports"] == 2 and adapters[0]["rejected_exports"] == 2
    assert adapters[0]["last_error"] == "unsupported_invalid_or_conflicting_usage"
    changed = copy.deepcopy(first)
    changed["attributes"].append(attribute("dispatcher.units", "2"))
    assert send(system, export_body([changed])).json()["partialSuccess"]["rejectedSpans"] == "1"
    assert len(system["client"].get("/api/events").json()) == 1


def test_otlp_scope_revocation_limits_and_invalid_types(system, monkeypatch):
    body = export_body([span()])
    assert system["client"].post("/api/otlp/v1/traces", json=body).status_code == 401
    assert send(system, export_body([span()], app="foreign")).status_code == 403
    assert (
        send(
            system,
            export_body([span()], **{"dispatcher.tenant_id": str(system["other"].tenant_id)}),
        ).status_code
        == 403
    )
    assert (
        send(
            system, export_body([span(), span(**{"tenant.id": str(system["other"].tenant_id)})])
        ).status_code
        == 403
    )
    assert system["client"].get("/api/overview").json()["counts"]["attempts"] == 0
    invalid = span(**{"gen_ai.usage.input_tokens": True})
    assert send(system, export_body([invalid])).json()["partialSuccess"]["rejectedSpans"] == "1"
    invalid = span()
    invalid["traceId"] = "-" + "1" * 31
    assert send(system, export_body([invalid])).json()["partialSuccess"]["rejectedSpans"] == "1"
    monkeypatch.setattr(system["db"].settings, "telemetry_max_bytes", 1024)
    assert send(system, export_body([span()] * 2)).status_code == 413
    system["auth"].revoke_key(system["owner"], system["key"]["id"])
    assert send(system, {}).status_code == 401


def test_otlp_references_merge_and_nested_tool_charges_remain_distinct(system):
    billed = event(source="provider-observer", reported_cost="0.08", reported_currency="USD")
    assert ingest(system, [billed]).status_code == 202
    reference = span(
        **{
            "dispatcher.canonical_source": "provider-observer",
            "dispatcher.attempt_id": billed["attempt_id"],
        }
    )
    tool = span(
        **{
            "gen_ai.operation.name": "execute_tool",
            "dispatcher.billable_attempt": True,
            "dispatcher.resource_kind": "tool",
            "dispatcher.operation": "lookup",
            "dispatcher.provider": "fixture-mcp",
            "dispatcher.cost": "0.02",
        }
    )
    assert send(system, export_body([reference, tool, span()])).json() == {}
    overview = system["client"].get("/api/overview").json()
    assert overview["counts"]["attempts"] == 3
    assert sum(Decimal(row["cost"]) for row in overview["totals"]) == Decimal("0.16")
    coverage = system["client"].get("/api/coverage").json()
    assert coverage["references"][0]["matched"] == 1 and not coverage["gaps"]

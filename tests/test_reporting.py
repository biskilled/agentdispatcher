"""Dashboard totals, groupings and drilldowns must apply identical access and date filters."""

from datetime import UTC, datetime, timedelta

from dispatcher.contracts import UsageEvent
from dispatcher.ledger import Ledger
from test_access import invite_user
from test_integration import event, ingest


def test_filter_breakdowns_drilldown_and_unknown_dimensions(system):
    client = system["client"]
    now = datetime.now(UTC)
    first = event(
        model="model-a",
        source="scheduler",
        session_id="first",
        trace_id="shared-trace",
        work_item="TA1",
        occurred_at=(now - timedelta(hours=2)).isoformat(),
    )
    second = event(model="model-b", source="interactive", session_id="second", work_item="TA2")
    ingest(system, [first, second])
    filters = {"model": "model-a", "source": "scheduler", "group_by": "session_id"}
    overview = client.get("/api/overview", params=filters).json()
    assert overview["counts"]["attempts"] == 1
    assert overview["groups"][0]["label"] == "first"
    assert overview["trend"][0]["attempts"] == 1
    assert len(client.get("/api/events", params=filters).json()) == 1
    assert client.get("/api/events/" + first["event_id"]).json()["payload"]["work_item"] == "TA1"
    assert (
        client.get(
            "/api/events/" + first["event_id"],
            headers={"X-Tenant-ID": str(system["other"].tenant_id)},
        ).status_code
        == 403
    )
    trace = {"trace_id": "shared-trace", "group_by": "trace_id"}
    assert client.get("/api/overview", params=trace).json()["groups"][0]["label"] == "shared-trace"
    assert len(client.get("/api/export/events", params=trace).json()["events"]) == 1
    params = {"from_time": (now - timedelta(hours=1)).isoformat()}
    assert client.get("/api/overview", params=params).json()["counts"]["attempts"] == 1
    assert (
        client.get("/api/overview", params={"group_by": "cost;DROP TABLE mem_usage"}).status_code
        == 422
    )
    assert (
        client.get(
            "/api/overview", params={"from_time": now.isoformat(), "to_time": now.isoformat()}
        ).status_code
        == 422
    )


def test_export_preserves_scope_precision_and_refuses_truncation(system, monkeypatch):
    client = system["client"]
    value = event(reported_cost="0.123456789012345678", reported_currency="USD", source="export")
    assert ingest(system, [value, event(source="another")]).status_code == 202
    foreign = system["auth"].issue_key(system["other"], "foreign", "trader", "test")
    Ledger(system["db"]).ingest(
        system["auth"].service(foreign["secret"]), [UsageEvent.model_validate(event())]
    )
    response = client.get("/api/export/events", params={"source": "export"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["events"][0]["cost"] == "0.123456789012345678"
    assert len(client.get("/api/export/events").json()["events"]) == 2
    assert (
        client.get(
            "/api/export/events", headers={"X-Tenant-ID": str(system["other"].tenant_id)}
        ).status_code
        == 403
    )
    monkeypatch.setattr(system["db"].settings, "export_rows", 1)
    assert client.get("/api/export/events").status_code == 413
    monkeypatch.setattr(system["db"].settings, "export_rows", 10)
    session, _, _ = invite_user(system, "member")
    client.cookies.set("dispatcher_session", session)
    assert client.get("/api/export/events").json()["events"] == []

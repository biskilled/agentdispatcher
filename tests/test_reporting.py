"""Dashboard totals, groupings and drilldowns must apply identical access and date filters."""

from datetime import UTC, datetime, timedelta

from test_integration import event, ingest


def test_filter_breakdowns_drilldown_and_unknown_dimensions(system):
    client = system["client"]
    now = datetime.now(UTC)
    first = event(
        model="model-a",
        source="scheduler",
        session_id="first",
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

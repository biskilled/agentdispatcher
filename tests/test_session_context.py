"""Event-time switches preserve prior costs, replay identity and tenant boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from test_integration import event, ingest


def change(system, at, **attributes):
    """Publish an explicit scoped context snapshot through the actual intake route."""
    body = {
        "id": str(uuid4()),
        "app": "trader",
        "environment": "test",
        "session_id": "caller-session",
        "effective_at": at.isoformat(),
        **attributes,
    }
    result = system["client"].post(
        "/api/sessions/context",
        json=body,
        headers={"Authorization": "Bearer " + system["key"]["secret"]},
    )
    return body, result


def test_switch_is_effective_time_scoped_and_never_rewrites(system):
    client = system["client"]
    started = datetime.now(UTC) - timedelta(hours=1)
    body, result = change(
        system, started, project="agentdesk", work_item="TA1", pipeline_role="researcher"
    )
    assert result.status_code == 202
    first = event(
        session_id="caller-session", occurred_at=(started + timedelta(seconds=1)).isoformat()
    )
    assert ingest(system, [first]).status_code == 202
    _, result = change(
        system, started + timedelta(seconds=2), work_item="TA2", pipeline_role="reviewer"
    )
    assert result.status_code == 202
    second = event(
        session_id="caller-session", occurred_at=(started + timedelta(seconds=3)).isoformat()
    )
    late = event(
        session_id="caller-session", occurred_at=(started + timedelta(seconds=1)).isoformat()
    )
    assert ingest(system, [second, late]).status_code == 202
    assert ingest(system, [first]).json()["duplicates"] == 1
    groups = client.get("/api/overview?group_by=work_item").json()["groups"]
    assert {row["label"]: row["attempts"] for row in groups} == {"TA1": 2, "TA2": 1}
    assert client.get("/api/overview?pipeline_role=reviewer").json()["counts"]["attempts"] == 1
    # A late mapping correction can affect future intake, but cannot move already accepted costs.
    _, result = change(system, started + timedelta(microseconds=1), work_item="TA3")
    assert result.status_code == 202
    assert ingest(system, [first]).json()["duplicates"] == 1
    assert client.get("/api/overview?work_item=TA1").json()["counts"]["attempts"] == 2
    explicit = event(session_id="caller-session", work_item=None, pipeline_role="manual")
    assert ingest(system, [explicit]).status_code == 202
    assert client.get("/api/events/" + explicit["event_id"]).json()["payload"]["work_item"] is None
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    assert (
        client.post("/api/sessions/context", json=body, headers=headers).json()["inserted"] is False
    )
    assert (
        client.post(
            "/api/sessions/context", json={**body, "work_item": "changed"}, headers=headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/sessions/context", json={**body, "app": "escape"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/sessions/context", json={**body, "user_id": "spoof"}, headers=headers
        ).status_code
        == 422
    )
    client.delete("/api/keys/" + system["key"]["id"])
    assert client.post("/api/sessions/context", json=body, headers=headers).status_code == 401

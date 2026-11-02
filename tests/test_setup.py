"""First-run evidence is tenant scoped, role gated and never a claim of external connectivity."""

from datetime import UTC, datetime

from dispatcher.contracts import UsageEvent
from dispatcher.ledger import Ledger
from test_access import invite_user
from test_integration import event, ingest

_SQL_HEARTBEAT = "INSERT INTO mem_worker_health(tenant_id,last_seen) VALUES(%s,%s)"


def test_setup_evidence_isolated_and_configured_not_verified(system):
    client, db = system["client"], system["db"]
    status = client.get("/api/setup/status").json()
    assert status["database_ready"] and not status["worker"]["healthy"]
    assert status["sources"] == []
    assert not status["configured"]["google"] and not status["configured"]["https"]
    assert ingest(system, [event(source="fixture-source")]).status_code == 202
    other = system["auth"].issue_key(system["other"], "other", "foreign-app", "test")
    Ledger(db).ingest(
        system["auth"].service(other["secret"]),
        [UsageEvent.model_validate(event(app="foreign-app", source="secret-source"))],
    )
    with db.tenant(system["owner"].tenant_id) as connection:
        connection.execute(_SQL_HEARTBEAT, (system["owner"].tenant_id, datetime.now(UTC)))
    status = client.get("/api/setup/status").json()
    assert status["worker"]["healthy"]
    assert len(status["sources"]) == 1
    assert status["sources"][0]["source"] == "fixture-source"
    assert not status["sources"][0]["stale"]
    assert "secret-source" not in str(status)
    assert system["key"]["secret"] not in str(status)
    assert (
        client.get(
            "/api/setup/status", headers={"X-Tenant-ID": str(system["other"].tenant_id)}
        ).status_code
        == 403
    )
    session, _, _ = invite_user(system, "member")
    client.cookies.set("dispatcher_session", session)
    assert client.get("/api/setup/status").status_code == 403

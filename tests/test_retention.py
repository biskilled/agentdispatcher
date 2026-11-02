"""Retention removes attribution without financial drift; tenant deletion never broadens scope."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from dispatcher.contracts import UsageEvent
from dispatcher.ledger import Ledger
from dispatcher.observations import Observation, Observations
from dispatcher.retention import Retention
from dispatcher.tenant_admin import delete_tenant
from test_access import invite_user
from test_integration import event, ingest

_SQL_AGE_OBSERVATION = "UPDATE mem_observations SET created_at=%s WHERE tenant_id=%s"
_SQL_OBSERVATION = "SELECT payload,attribution_expired_at FROM mem_observations WHERE tenant_id=%s"


def test_attribution_retention_preserves_charges_replay_and_other_tenant(system, monkeypatch):
    now = datetime.now(UTC)
    old = event(
        occurred_at=(now - timedelta(days=60)).isoformat(),
        user_id="reported-user",
        session_id="old-session",
        work_item="old-work",
        reported_cost="0.12",
        reported_currency="USD",
    )
    recent = event(user_id="recent-user", reported_cost="0.34", reported_currency="USD")
    assert ingest(system, [old, recent]).status_code == 202
    foreign = system["auth"].issue_key(system["other"], "other", "trader", "test")
    ledger = Ledger(system["db"])
    ledger.ingest(system["auth"].service(foreign["secret"]), [UsageEvent.model_validate(old)])
    service = Retention(system["db"])
    tenant = system["owner"].tenant_id
    Observations(system["db"]).ingest(
        system["auth"].service(system["key"]["secret"]),
        [
            Observation(
                event=UsageEvent.model_validate(
                    {**old, "event_id": str(uuid4()), "source": "client"}
                ),
                expected_source=old["source"],
            ),
        ],
    )
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        connection.execute(_SQL_AGE_OBSERVATION, (now - timedelta(days=60), tenant))

    def tick():
        with system["db"].tenant(tenant) as connection:
            return service.tick(connection, tenant, now)

    assert tick() == {}
    client = system["client"]
    assert client.get("/api/retention").json() == {"attribution_days": None, "revision": 0}
    assert (
        client.put("/api/retention", json={"attribution_days": 30, "revision": 0}).status_code
        == 200
    )
    assert (
        client.put("/api/retention", json={"attribution_days": 1, "revision": 0}).status_code == 409
    )
    monkeypatch.setattr(system["db"].settings, "retention_batch_rows", 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        processed = list(pool.map(lambda _: tick(), range(2)))
    assert sum(row["mem_usage"] for row in processed) == 1
    assert sum(row["mem_observations"] for row in processed) == 1
    with system["db"].tenant(tenant) as connection:
        reference = connection.execute(_SQL_OBSERVATION, (tenant,)).fetchone()
        assert reference["attribution_expired_at"] and reference["payload"]["user_id"] is None
    rows = client.get("/api/events").json()
    expired = next(row for row in rows if row["event_id"] == old["event_id"])
    assert expired["cost"] == "0.12" and expired["user_attribution"] == "expired"
    assert expired["payload"]["user_id"] is None and expired["payload"]["session_id"] is None
    assert ledger.events(system["other"])[0]["payload"]["user_id"] == "reported-user"
    assert ingest(system, [old]).json()["duplicates"] == 1
    assert len(client.get("/api/export/events").json()["events"]) == 2
    session, _, _ = invite_user(system)
    client.cookies.set("dispatcher_session", session)
    assert client.get("/api/retention").status_code == 403
    assert (
        client.put("/api/retention", json={"attribution_days": 1, "revision": 1}).status_code == 403
    )


def test_tenant_erasure_confirmation_and_isolation(system):
    assert ingest(system, [event()]).status_code == 202
    other_key = system["auth"].issue_key(system["other"], "other", "trader", "test")
    ledger = Ledger(system["db"])
    ledger.ingest(system["auth"].service(other_key["secret"]), [UsageEvent.model_validate(event())])
    tenant = system["owner"].tenant_id
    with pytest.raises(ValueError, match="confirmation"):
        delete_tenant(os.environ["TEST_DATABASE_URL"], tenant, uuid4())
    assert len(ledger.events(system["owner"])) == 1
    deleted = delete_tenant(os.environ["TEST_DATABASE_URL"], tenant, tenant)
    assert deleted["deleted_rows"]["mem_usage"] == 1
    assert len(ledger.events(system["other"])) == 1
    assert system["auth"].service(other_key["secret"]).tenant_id == system["other"].tenant_id
    assert system["client"].get("/api/export/events").status_code == 403

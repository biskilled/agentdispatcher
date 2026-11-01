"""Critical failure paths exercise the API and non-bypass PostgreSQL roles together."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from dispatcher.auth import verifier
from dispatcher.contracts import UsageEvent
from dispatcher.ledger import Ledger

_SQL_KEYS = "SELECT token_hash FROM mng_sdk_keys WHERE id=%s"
_SQL_USAGE = "SELECT tenant_id FROM mem_usage"
_SQL_AUTH_FORBIDDEN = "SELECT * FROM mng_sessions"
_SQL_SET_ROLE = "UPDATE mng_memberships SET role=%s WHERE tenant_id=%s AND user_id=%s"
_SQL_REMOVE = "DELETE FROM mng_memberships WHERE tenant_id=%s AND user_id=%s"
_SQL_EXPIRE = "UPDATE mng_sdk_keys SET expires_at=now() - interval '1 second' WHERE id=%s"
_SQL_STALE = "UPDATE mem_job_runs SET received_at=now() - interval '1 day' WHERE tenant_id=%s"


def event(**updates):
    """Build one explicit synthetic attempt with stable IDs for replay tests."""
    return {
        "event_id": str(uuid4()),
        "attempt_id": str(uuid4()),
        "operation_id": str(uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "app": "trader",
        "environment": "test",
        "resource_kind": "api",
        "source": "fixture",
        "provider": "synthetic",
        "operation": "price",
        "api_id": "market",
        "status": "success",
        "status_code": 200,
        "duration_ms": "12.5",
        **updates,
    }


def ingest(system, events):
    """Submit a batch through the same key authentication route as a deployed SDK."""
    return system["client"].post(
        "/api/ingest",
        json={"events": events},
        headers={"Authorization": "Bearer " + system["key"]["secret"]},
    )


def test_login_replay_logout_csrf_and_hash_only_storage(system):
    client = system["client"]
    assert (
        client.post("/api/auth/email/consume", json={"token": system["token"]}).status_code == 401
    )
    with system["db"].auth() as connection:
        row = connection.execute(_SQL_KEYS, (system["key"]["id"],)).fetchone()
    assert row["token_hash"] == verifier(system["key"]["secret"])
    assert system["key"]["secret"] not in str(client.get("/api/keys").json())
    assert (
        client.post(
            "/api/keys",
            json={"name": "bad", "app": "x", "environment": "test"},
            headers={"Origin": "https://attacker.invalid"},
        ).status_code
        == 403
    )
    cookie = client.cookies.get("dispatcher_session")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("dispatcher_session", cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_scope_batch_atomicity_and_database_rls(system):
    good = event()
    bad = event(tenant_id=str(system["other"].tenant_id))
    assert ingest(system, [good, bad]).status_code == 403
    assert system["client"].get("/api/overview").json()["counts"]["attempts"] == 0
    assert ingest(system, [event(app="forged")]).status_code == 403
    assert ingest(system, [good]).status_code == 202
    assert (
        system["client"]
        .get("/api/events", headers={"X-Tenant-ID": str(system["other"].tenant_id)})
        .status_code
        == 403
    )
    with system["db"].tenant(system["other"].tenant_id) as connection:
        assert connection.execute(_SQL_USAGE).fetchall() == []
    with system["db"].tenant(system["owner"].tenant_id) as connection:
        assert len(connection.execute(_SQL_USAGE).fetchall()) == 1
    with psycopg.connect(system["db"].settings.database_url.get_secret_value()) as connection:
        assert connection.execute(_SQL_USAGE).fetchall() == []
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(_SQL_AUTH_FORBIDDEN)


def test_deduplication_conflicting_replays_and_real_retries(system):
    first = event()
    assert ingest(system, [first]).json() == {"inserted": 1, "duplicates": 0}
    assert ingest(system, [first]).json() == {"inserted": 0, "duplicates": 1}
    assert ingest(system, [{**first, "units": "999"}]).status_code == 409
    second = event(operation_id=first["operation_id"])
    assert ingest(system, [second]).status_code == 202
    overview = system["client"].get("/api/overview").json()
    assert overview["counts"]["attempts"] == 2
    assert overview["counts"]["unknown_cost"] == 2
    assert overview["totals"][0]["cost"] is None


def test_concurrent_exports_count_once(system):
    principal = system["auth"].service(system["key"]["secret"])
    model = UsageEvent.model_validate(event())
    ledger = Ledger(system["db"])
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: ledger.ingest(principal, [model]), range(8)))
    assert sum(item["inserted"] for item in results) == 1


def test_pricing_versions_zero_unknown_and_timeout(system):
    client = system["client"]
    effective = datetime.now(UTC) - timedelta(days=1)
    plan = {
        "api_id": "market",
        "name": "Synthetic only",
        "effective_at": effective.isoformat(),
        "pricing": "per_unit",
        "unit_price": "0.05",
    }
    assert client.post("/api/plans", json=plan).status_code == 201
    assert (
        ingest(
            system,
            [
                event(units="3"),
                event(status="error", status_code=429),
                event(status="timeout", status_code=None),
            ],
        ).status_code
        == 202
    )
    plan["effective_at"] = datetime.now(UTC).isoformat()
    plan["unit_price"] = "0.20"
    assert client.post("/api/plans", json=plan).status_code == 201
    assert ingest(system, [event(units="2")]).status_code == 202
    rows = client.get("/api/events").json()
    assert sorted(Decimal(row["cost"]) for row in rows if row["cost"] is not None) == [
        Decimal("0"),
        Decimal("0.15"),
        Decimal("0.40"),
    ]
    assert sum(row["cost"] is None for row in rows) == 1
    free = {
        "api_id": "free",
        "name": "Free fixture",
        "effective_at": effective.isoformat(),
        "pricing": "free",
    }
    assert client.post("/api/plans", json=free).status_code == 201
    ingest(system, [event(api_id="free")])
    assert client.get("/api/events").json()[0]["cost_kind"] == "configured_free"


def test_keys_expiry_revocation_and_no_admin_privileges(system):
    assert ingest(system, [event()]).status_code == 202
    client = system["client"]
    with system["db"].auth() as connection:
        connection.execute(_SQL_EXPIRE, (system["key"]["id"],))
    assert ingest(system, [event()]).status_code == 401
    system["key"] = client.post(
        "/api/keys", json={"name": "replacement", "app": "trader", "environment": "test"}
    ).json()
    assert (
        client.delete(
            "/api/keys/" + system["key"]["id"],
            headers={"X-Tenant-ID": str(system["other"].tenant_id)},
        ).status_code
        == 403
    )
    assert client.delete("/api/keys/" + system["key"]["id"]).status_code == 204
    assert ingest(system, [event()]).status_code == 401
    client.cookies.clear()
    assert (
        client.get(
            "/api/keys", headers={"Authorization": "Bearer " + system["key"]["secret"]}
        ).status_code
        == 401
    )


def test_membership_removal_and_role_changes_are_immediate(system):
    client = system["client"]
    with system["db"].auth() as connection:
        connection.execute(
            _SQL_SET_ROLE, ("viewer", system["owner"].tenant_id, system["owner"].subject_id)
        )
    assert client.get("/api/keys").status_code == 403
    assert client.get("/api/overview").status_code == 403
    with system["db"].auth() as connection:
        connection.execute(_SQL_REMOVE, (system["owner"].tenant_id, system["owner"].subject_id))
    assert client.get("/api/auth/me").json()["tenants"] == []
    assert client.get("/api/events").status_code == 403


def test_job_out_of_order_and_stale_health(system):
    client = system["client"]
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    started = datetime.now(UTC)
    run = {
        "run_id": str(uuid4()),
        "app": "trader",
        "environment": "test",
        "name": "scan",
        "state": "running",
        "occurred_at": started.isoformat(),
    }
    assert client.post("/api/jobs/events", json=run, headers=headers).status_code == 202
    with system["db"].tenant(system["owner"].tenant_id) as connection:
        connection.execute(_SQL_STALE, (system["owner"].tenant_id,))
    Ledger(system["db"]).tick()
    assert client.get("/api/jobs").json()[0]["stale"] is True
    finish = {
        **run,
        "state": "completed",
        "occurred_at": (started + timedelta(seconds=2)).isoformat(),
    }
    assert client.post("/api/jobs/events", json=finish, headers=headers).status_code == 202
    assert client.post("/api/jobs/events", json=run, headers=headers).status_code == 409
    assert client.get("/api/jobs").json()[0]["state"] == "completed"
    assert client.get("/api/jobs").json()[0]["stale"] is False


def test_no_automatic_google_email_linking(system):
    claims = {
        "iss": "https://accounts.google.com",
        "sub": uuid4().hex,
        "email": system["email"],
        "email_verified": True,
    }
    session = system["auth"].google_login(claims)
    assert system["auth"].user(session)["tenants"] == []
    assert system["auth"].user(session)["user_id"] != system["owner"].subject_id


def test_ingestion_rejects_sensitive_unknown_fields(system):
    assert ingest(system, [event(prompt="never persist this")]).status_code == 422
    assert ingest(system, [event(duration_ms="NaN")]).status_code == 422

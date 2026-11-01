"""Durable schedule, budget and reconciliation fixtures exercise restart and late evidence."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from dispatcher.operations import Operations
from test_integration import event, ingest
from test_pricing import connection, plan


def test_missing_schedule_late_completion_and_scope(system):
    client = system["client"]
    start = datetime(2026, 10, 30, tzinfo=UTC)
    schedule = {
        "id": "scan",
        "name": "Scan",
        "app": "trader",
        "environment": "test",
        "first_expected": start.isoformat(),
        "cadence": {"kind": "fixed", "seconds": 3600, "anchor": start.isoformat()},
        "grace_seconds": 60,
    }
    assert client.put("/api/schedules", json={"config": schedule}).status_code == 200
    operations = Operations(system["db"])
    operations.tick(system["owner"].tenant_id, start + timedelta(seconds=61))
    health = client.get("/api/schedules/health").json()
    assert len(health) == 1 and health[0]["state"] == "missed"
    # A fresh process resumes the persisted cursor, without duplicate expected occurrences.
    Operations(system["db"]).tick(system["owner"].tenant_id, start + timedelta(seconds=62))
    assert len(client.get("/api/schedules/health").json()) == 1
    run = {
        "run_id": str(uuid4()),
        "app": "trader",
        "environment": "test",
        "name": "Scan",
        "state": "completed",
        "occurred_at": (start + timedelta(seconds=20)).isoformat(),
        "schedule_id": "scan",
        "scheduled_for": start.isoformat(),
    }
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    assert client.post("/api/jobs/events", json=run, headers=headers).status_code == 202
    assert client.get("/api/schedules/health").json()[0]["state"] == "completed"
    assert operations.health(system["other"]) == []
    assert (
        client.post("/api/jobs/events", json={**run, "app": "wrong"}, headers=headers).status_code
        == 403
    )
    assert (
        client.post(
            "/api/jobs/events",
            json={**run, "scheduled_for": (start + timedelta(seconds=1)).isoformat()},
            headers=headers,
        ).status_code
        == 422
    )


def test_budget_fees_refunds_and_provider_statements_do_not_double_count(system):
    client = system["client"]
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    connection(client, "one")
    tariff = plan(billing_window={"kind": "monthly"})
    assert client.post("/api/plans", json=tariff).status_code == 201
    usage = event(connection_id="one", units="9")
    ingest(system, [usage])
    budget = {"id": "total", "amount": "10", "window": {"kind": "monthly"}}
    assert client.put("/api/budgets", json={"config": budget}).status_code == 200
    assert client.get("/api/budgets/usage").json()[0]["known_amount"] == "11.00"
    refund = {
        "event_id": usage["event_id"],
        "amount": "-0.50",
        "currency": "USD",
        "source_ref": "synthetic-refund",
        "reason": "Synthetic provider refund fixture",
    }
    first = client.post("/api/adjustments", json=refund)
    assert first.status_code == 201
    assert client.post("/api/adjustments", json=refund).json() == first.json()
    assert client.post("/api/adjustments", json={**refund, "amount": "-9"}).status_code == 409
    assert client.get("/api/budgets/usage").json()[0]["known_amount"] == "10.50"
    statement = {
        "pool": "market:account:shared",
        "provider_ref": "synthetic-invoice",
        "period_start": start.isoformat(),
        "period_end": (now + timedelta(days=1)).isoformat(),
        "observed_at": now.isoformat(),
        "amount": "10.75",
        "currency": "USD",
        "units": "9",
        "source_note": "Synthetic statement; no live vendor terms",
    }
    assert client.post("/api/reconciliation", json=statement).status_code == 201
    assert client.post("/api/reconciliation", json=statement).status_code == 201
    report = client.get("/api/reconciliation").json()[0]
    assert report["observed_amount"] == "10.50" and report["drift"] == "0.25"
    assert report["stale"] is False
    assert client.get("/api/budgets/usage").json()[0]["known_amount"] == "10.50"
    assert client.get("/api/events").json()[0]["cost"] == "1.00"
    assert (
        client.post("/api/reconciliation", json={**statement, "amount": "900"}).status_code == 409
    )
    operations = Operations(system["db"])
    operations.tick(system["owner"].tenant_id, now)
    Operations(system["db"]).tick(system["owner"].tenant_id, now + timedelta(seconds=1))
    alerts = client.get("/api/alerts").json()
    assert len([a for a in alerts if a["kind"] == "budget.threshold"]) == 2
    assert (
        client.post(
            "/api/adjustments", json=refund, headers={"X-Tenant-ID": str(system["other"].tenant_id)}
        ).status_code
        == 403
    )

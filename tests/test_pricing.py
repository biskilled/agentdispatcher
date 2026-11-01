"""Synthetic tariff fixtures verify monetary arithmetic, reset boundaries and pool isolation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from dispatcher.contracts import ApiPlan, UsageEvent, Window
from dispatcher.pricing import cumulative_cost, window_bounds
from test_access import invite_user
from test_integration import event, ingest


def plan(**changes):
    """Use synthetic prices only; this fixture makes no claim about vendor contracts."""
    return {
        "api_id": "market",
        "name": "Synthetic tariff",
        "source_note": "Synthetic test only",
        "effective_at": (datetime.now(UTC) - timedelta(days=60)).isoformat(),
        "pricing": "subscription",
        "unit_price": "0.25",
        "fixed_fee": "10",
        "included_units": "5",
        "billing_window": {"kind": "monthly", "timezone": "Europe/London"},
        "pool_scope": "account",
        "quota_rules": [
            {
                "name": "minute",
                "limit": "10",
                "window": {"kind": "rolling", "seconds": 60},
                "statuses": [200, 429],
                "thresholds": [50, 100],
            }
        ],
        **changes,
    }


def connection(client, name, pool="shared"):
    """Create independent connections drawing from one administrator-defined account pool."""
    result = client.put(
        "/api/connections",
        json={
            "config": {
                "id": name,
                "api_id": "market",
                "name": name,
                "account_pool": pool,
                "operations": ["price"],
            },
            "revision": 0,
        },
    )
    assert result.status_code == 200, result.text


def test_shared_subscription_quota_retries_late_events_and_fees(system):
    client = system["client"]
    for name in ["one", "two"]:
        connection(client, name)
    assert client.post("/api/plans", json=plan()).status_code == 201
    first = event(connection_id="one", units="3")
    second = event(connection_id="two", units="4")
    assert ingest(system, [first, second]).status_code == 202
    assert ingest(system, [first, second]).json()["duplicates"] == 2
    assert (
        ingest(
            system,
            [
                event(connection_id="one", status="error", status_code=429, units="2"),
                event(connection_id="one", status="timeout", status_code=None),
                event(connection_id="two", status="cached", units="20"),
            ],
        ).status_code
        == 202
    )
    assert sum(
        Decimal(r["cost"]) for r in client.get("/api/events").json() if r["cost"] is not None
    ) == Decimal("0.50")
    quota = client.get("/api/quotas").json()[0]
    assert quota["units"] == "9" and quota["unknown_events"] == 1
    assert len(client.get("/api/charges").json()) == 1
    assert client.get("/api/charges").json()[0]["amount"] == "10"
    accounting = client.app.state.ledger.accounting
    now = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: accounting.tick(system["owner"].tenant_id, now), range(4)))
    assert len(client.get("/api/alerts").json()) == 1
    late = event(
        connection_id="two", units="1", occurred_at=(now - timedelta(seconds=30)).isoformat()
    )
    ingest(system, [late])
    # Keep this check in the same alert bucket even when CI runs at a minute boundary.
    accounting.tick(system["owner"].tenant_id, now)
    assert len(client.get("/api/alerts").json()) == 2
    assert accounting.quotas(system["other"])[0:] == []
    assert accounting.charges(system["other"]) == []
    assert accounting.quotas(system["owner"], now + timedelta(seconds=120))[0]["units"] == 0


def test_plan_history_preview_and_connection_concurrency(system):
    client = system["client"]
    connection(client, "one")
    config = client.get("/api/connections").json()[0]["config"]
    assert client.put("/api/connections", json={"config": config, "revision": 0}).status_code == 409
    assert client.post("/api/plans", json=plan()).status_code == 201
    original = event(connection_id="one", units="7")
    ingest(system, [original])
    before = client.get("/api/events").json()[0]
    revised = plan(effective_at=datetime.now(UTC).isoformat(), unit_price="0.50")
    assert client.post("/api/plans", json=revised).status_code == 201
    preview = client.post(
        "/api/plans/preview",
        json={"plan": revised, "event": event(units="2"), "previous_units": "7"},
    )
    assert preview.json()["cost"] == "1.00"
    ingest(system, [event(connection_id="one", units="2")])
    rows = client.get("/api/events").json()
    assert (
        next(row for row in rows if row["event_id"] == original["event_id"])["cost"]
        == before["cost"]
    )
    assert rows[0]["cost"] == "1.00"
    assert len(client.get("/api/charges").json()) == 1
    assert ingest(system, [event(connection_id="one", operation="unregistered")]).status_code == 422


@pytest.mark.parametrize("mode,total", [("graduated", "15"), ("volume", "10")])
def test_tiers_and_preview_share_exact_formula(mode, total):
    tariff = ApiPlan.model_validate(
        plan(
            pricing=mode,
            unit_price=None,
            fixed_fee="0",
            included_units="0",
            tiers=[{"up_to": "10", "unit_price": "1"}, {"up_to": None, "unit_price": "0.5"}],
        )
    )
    assert cumulative_cost(tariff, Decimal(20)) == Decimal(total)


def test_calendar_windows_cover_dst_and_fixed_reset():
    daily = Window(kind="daily", timezone="Europe/London")
    start, end = window_bounds(daily, datetime(2026, 3, 29, 12, tzinfo=UTC))
    assert (end - start).total_seconds() == 23 * 3600
    start, end = window_bounds(daily, datetime(2026, 10, 25, 12, tzinfo=UTC))
    assert (end - start).total_seconds() == 25 * 3600
    monthly = Window(kind="monthly", timezone="America/New_York", reset_day=15)
    start, end = window_bounds(monthly, datetime(2026, 3, 14, 12, tzinfo=UTC))
    assert start == datetime(2026, 2, 15, 5, tzinfo=UTC)
    assert end == datetime(2026, 3, 15, 4, tzinfo=UTC)
    fixed = Window(kind="fixed", seconds=60, anchor=datetime(2026, 1, 1, tzinfo=UTC))
    at = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    assert window_bounds(fixed, at)[0] == at


def test_concurrent_pool_ingestion_charges_subscription_once(system):
    client = system["client"]
    connection(client, "one")
    client.post("/api/plans", json=plan())
    principal = system["auth"].service(system["key"]["secret"])
    ledger = client.app.state.ledger
    events = [UsageEvent.model_validate(event(connection_id="one", units="2")) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda row: ledger.ingest(principal, [row]), events))
    assert sum(Decimal(row["cost"]) for row in client.get("/api/events").json()) == Decimal("1.75")
    assert len(client.get("/api/charges").json()) == 1


def test_custom_catalog_audit_and_role_boundaries(system):
    client = system["client"]
    tariff = plan(
        api_id="custom-units",
        name="Custom API",
        pricing="per_unit",
        fixed_fee="0",
        included_units="0",
        unit_name="data row",
        billing_window=None,
        pool_scope="api",
    )
    assert client.post("/api/plans", json=tariff).status_code == 201
    sample = event(api_id="custom-units", units="3")
    assert (
        client.post("/api/plans/preview", json={"plan": tariff, "event": sample}).json()["cost"]
        == "0.75"
    )
    assert ingest(system, [sample]).status_code == 202
    assert client.get("/api/events").json()[0]["cost"] == "0.75"
    audit = client.get("/api/catalog/history").json()
    assert audit[0]["after_value"]["unit_name"] == "data row"
    assert audit[0]["actor_id"] == str(system["owner"].subject_id)
    routes = ["/api/plans", "/api/connections", "/api/catalog/history"]
    for route in routes:
        assert (
            client.get(route, headers={"X-Tenant-ID": str(system["other"].tenant_id)}).status_code
            == 403
        )
    for role in ("member", "viewer"):
        session, _, _ = invite_user(system, role)
        client.cookies.clear()
        client.cookies.set("dispatcher_session", session)
        for route in routes:
            assert client.get(route).status_code == 403
        assert client.post("/api/plans", json=tariff).status_code == 403
        assert (
            client.post("/api/plans/preview", json={"plan": tariff, "event": sample}).status_code
            == 403
        )
    client.cookies.clear()
    for route in routes:
        assert (
            client.get(
                route, headers={"Authorization": "Bearer " + system["key"]["secret"]}
            ).status_code
            == 401
        )

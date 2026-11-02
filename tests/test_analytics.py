"""Analytics SQL must stay scoped even when generated queries actively change tenant filters."""

import os
import secrets
from decimal import Decimal

import psycopg
import pytest
from dispatcher.analytics import provision, revoke
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from test_integration import event, ingest

_SQL_COUNTS = "SELECT count(*) attempts,sum(input_tokens) input_tokens FROM llm_usage"
_SQL_COST = "SELECT currency,cost_kind,sum(cost) cost FROM llm_usage GROUP BY currency,cost_kind"
_SQL_GROUPS = "SELECT provider,count(*) attempts FROM llm_usage GROUP BY provider"
_SQL_FEATURE = "SELECT feature FROM llm_usage WHERE feature IS NOT NULL"
_SQL_SCOPE = "SELECT DISTINCT tenant_id FROM llm_usage"
_SQL_FORGED = "SELECT * FROM llm_usage WHERE tenant_id=%s"
_SQL_SETTING = "SELECT set_config('dispatcher.tenant_id',%s,false)"
_SQL_ROLE = "SET ROLE dispatcher_analytics"
_SQL_WRITE = "DELETE FROM mem_usage"
_SQL_PRIVATE = "SELECT * FROM mng_sessions"
_SQL_BINDINGS = "SELECT * FROM mng_analytics_roles"


def test_analytics_totals_isolation_rotation_and_revocation(system):
    client = system["client"]
    assert (
        ingest(
            system,
            [
                event(
                    input_tokens=7, reported_cost="1.25", reported_currency="USD", feature="summary"
                ),
                event(input_tokens=11, provider="second"),
            ],
        ).status_code
        == 202
    )
    dsn = os.environ["TEST_DATABASE_URL"]
    tenant = system["owner"].tenant_id
    password = secrets.token_urlsafe(32)
    role = provision(dsn, tenant, password)
    other_role = provision(dsn, system["other"].tenant_id, password)
    overview = client.get("/api/overview", params={"group_by": "provider"}).json()
    with psycopg.connect(
        make_conninfo(dsn, user=role, password=password), row_factory=dict_row, autocommit=True
    ) as connection:
        assert connection.execute(_SQL_FEATURE).fetchall() == [{"feature": "summary"}]
        counts = connection.execute(_SQL_COUNTS).fetchone()
        assert counts["attempts"] == overview["counts"]["attempts"] == 2
        assert counts["input_tokens"] == int(overview["counts"]["input_tokens"]) == 18
        costs = connection.execute(_SQL_COST).fetchall()
        expected = {
            (r["currency"], r["cost_kind"]): Decimal(r["cost"]) if r["cost"] else None
            for r in overview["totals"]
        }
        assert {(r["currency"], r["cost_kind"]): r["cost"] for r in costs} == expected
        groups = connection.execute(_SQL_GROUPS).fetchall()
        assert {r["provider"]: r["attempts"] for r in groups} == {
            r["label"]: r["attempts"] for r in overview["groups"]
        }
        connection.execute(_SQL_SETTING, (str(system["other"].tenant_id),))
        assert connection.execute(_SQL_FORGED, (system["other"].tenant_id,)).fetchall() == []
        connection.execute(_SQL_ROLE)
        assert connection.execute(_SQL_SCOPE).fetchall() == [{"tenant_id": tenant}]
        for forbidden in (_SQL_PRIVATE, _SQL_WRITE, _SQL_BINDINGS):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute(forbidden)
        assert provision(dsn, tenant, secrets.token_urlsafe(32)) == role
        revoke(dsn, tenant)
        assert connection.execute(_SQL_COUNTS).fetchone()["attempts"] == 0
    with psycopg.connect(make_conninfo(dsn, user=other_role, password=password)) as connection:
        assert connection.execute(_SQL_SCOPE).fetchall() == []

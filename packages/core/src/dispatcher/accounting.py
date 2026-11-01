"""Tenant-scoped accounting evidence without counting provider snapshots as new charges."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from dispatcher.auth import require_admin
from dispatcher.contracts import ApiConnection, ApiPlan, Principal, UsageEvent
from dispatcher.pricing import calculate_price, charged_units, quota_units, window_bounds

_SQL_CONNECTION = "SELECT revision,config FROM mng_connections WHERE tenant_id=%s AND id=%s"
_SQL_CONNECTIONS = (
    "SELECT id,revision,config,updated_at FROM mng_connections WHERE tenant_id=%s ORDER BY id"
)
_SQL_UPSERT = """
INSERT INTO mng_connections(tenant_id,id,revision,config) VALUES(%s,%s,1,%s)
ON CONFLICT(tenant_id,id) DO UPDATE SET revision=mng_connections.revision+1,
config=EXCLUDED.config,updated_at=now() WHERE mng_connections.revision=%s RETURNING revision
"""
_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_AUDIT = """
INSERT INTO mem_config_audit(tenant_id,id,actor_id,resource,action,before_value,after_value)
VALUES(%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_UNITS = """
SELECT coalesce(sum(units),0) units FROM mem_usage_ratings WHERE tenant_id=%s AND pool=%s
AND occurred_at >= %s AND occurred_at < %s
"""
_SQL_RATING = """
INSERT INTO mem_usage_ratings(tenant_id,event_id,pool,billing_start,billing_end,
units,plan_id,occurred_at)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_FEE = """
INSERT INTO mem_period_charges(tenant_id,pool,period_start,period_end,plan_id,amount,currency)
VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
"""
_SQL_FEES = (
    "SELECT * FROM mem_period_charges WHERE tenant_id=%s ORDER BY period_start DESC LIMIT %s"
)
_SQL_QUOTA_EVENT = """
INSERT INTO mem_quota_events(tenant_id,event_id,pool,rule_name,units,occurred_at,plan_id)
VALUES(%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_POOLS = """
SELECT DISTINCT ON(pool) pool,p.plan FROM mem_usage_ratings r JOIN mng_api_plans original
ON (original.tenant_id,original.id)=(r.tenant_id,r.plan_id)
JOIN mng_api_plans p ON p.tenant_id=r.tenant_id AND p.api_id=original.api_id
WHERE r.tenant_id=%s AND p.effective_at<=%s ORDER BY pool,p.effective_at DESC
"""
_SQL_QUOTA = """
SELECT coalesce(sum(units),0) units, count(*) FILTER(WHERE units IS NULL) unknown_events
FROM mem_quota_events WHERE tenant_id=%s AND pool=%s AND rule_name=%s
AND occurred_at >= %s AND occurred_at < %s
"""
_SQL_ALERT = """
INSERT INTO mem_alerts(tenant_id,id,dedup_key,kind,evidence) VALUES(%s,%s,%s,%s,%s)
ON CONFLICT(tenant_id,dedup_key) DO NOTHING
"""
_SQL_ALERTS = """
SELECT id,kind,evidence,created_at FROM mem_alerts WHERE tenant_id=%s
ORDER BY created_at DESC LIMIT %s
"""
_SQL_HISTORY = """
SELECT id,actor_id,resource,action,before_value,after_value,created_at
FROM mem_config_audit WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s
"""


def audit(connection, principal: Principal, resource: str, action: str, before, after):
    """Append metadata-only configuration history within the caller's transaction."""
    connection.execute(
        _SQL_AUDIT,
        (
            principal.tenant_id,
            uuid4(),
            principal.subject_id,
            resource,
            action,
            Jsonb(before),
            Jsonb(after),
        ),
    )


def emit_alert(connection, tenant_id, key: str, kind: str, evidence: dict):
    """Persist one notification for a stable crossing key, even with overlapping workers."""
    connection.execute(
        _SQL_ALERT,
        (
            tenant_id,
            uuid4(),
            key,
            kind,
            Jsonb(jsonable_encoder(evidence, custom_encoder={Decimal: str})),
        ),
    )


class Accounting:
    """Share catalog validation, pool serialization and pricing across all intake adapters."""

    def __init__(self, db):
        self.db = db

    def connections(self, principal):
        """Return configured connections without provider secrets."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(_SQL_CONNECTIONS, (principal.tenant_id,)).fetchall()

    def history(self, principal):
        """Expose authorised configuration audit evidence without modifying historical versions."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_HISTORY, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()

    def put_connection(self, principal, config: ApiConnection, revision: int):
        """Create with revision zero or update an exact revision; stale forms cannot overwrite."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            connection.execute(_SQL_LOCK, (f"{principal.tenant_id}:connection:{config.id}",))
            previous = connection.execute(
                _SQL_CONNECTION, (principal.tenant_id, config.id)
            ).fetchone()
            if (previous["revision"] if previous else 0) != revision:
                raise HTTPException(409, "Connection changed; reload before saving")
            result = connection.execute(
                _SQL_UPSERT,
                (principal.tenant_id, config.id, Jsonb(config.model_dump(mode="json")), revision),
            ).fetchone()
            audit(
                connection,
                principal,
                "connection:" + config.id,
                "connection.saved",
                previous["config"] if previous else None,
                config.model_dump(mode="json"),
            )
            return result

    def pool(self, connection, tenant_id, plan: ApiPlan, event: UsageEvent) -> str:
        """Resolve a configured pool; never accept a caller-controlled account pool tag."""
        configured = None
        if event.connection_id:
            row = connection.execute(_SQL_CONNECTION, (tenant_id, event.connection_id)).fetchone()
            if not row:
                raise HTTPException(422, "Unknown API connection")
            configured = ApiConnection.model_validate(row["config"])
            if not configured.enabled or configured.api_id != event.api_id:
                raise HTTPException(422, "Connection is disabled or belongs to another API")
            if configured.operations and event.operation not in configured.operations:
                raise HTTPException(422, "Operation is not registered for this connection")
        if plan.pool_scope in {"connection", "account"} and configured is None:
            raise HTTPException(422, "This pricing plan requires a registered connection")
        parts = [plan.api_id, plan.pool_scope]
        if plan.pool_scope == "connection":
            parts.append(configured.id)
        elif plan.pool_scope == "account":
            parts.append(configured.account_pool)
        elif plan.pool_scope == "endpoint":
            parts.append(event.operation)
        return ":".join(parts)

    def prepare(self, connection, principal, plan, event):
        """Serialize shared-pool billing; cumulative rates use observed arrival allocation."""
        pool = self.pool(connection, principal.tenant_id, plan, event)
        connection.execute(_SQL_LOCK, (f"{principal.tenant_id}:pool:{pool}",))
        start = end = None
        previous = Decimal(0)
        if plan.billing_window:
            start, end = window_bounds(plan.billing_window, event.occurred_at)
            previous = connection.execute(
                _SQL_UNITS, (principal.tenant_id, pool, start, end)
            ).fetchone()["units"]
        return (pool, start, end), calculate_price(plan, event, previous)

    def record(self, connection, principal, plan_id, plan, event, context):
        """Persist evidence only for newly inserted attempts in the same transaction."""
        pool, start, end = context
        connection.execute(
            _SQL_RATING,
            (
                principal.tenant_id,
                event.event_id,
                pool,
                start,
                end,
                charged_units(plan, event),
                plan_id,
                event.occurred_at,
            ),
        )
        if plan.fixed_fee:
            connection.execute(
                _SQL_FEE,
                (principal.tenant_id, pool, start, end, plan_id, plan.fixed_fee, plan.currency),
            )
        for rule in plan.quota_rules:
            connection.execute(
                _SQL_QUOTA_EVENT,
                (
                    principal.tenant_id,
                    event.event_id,
                    pool,
                    rule.name,
                    quota_units(rule, event),
                    event.occurred_at,
                    plan_id,
                ),
            )

    def quota_state(self, connection, tenant_id, pool, rule, at):
        """Report locally observed consumption and uncertainty without enforcing a quota."""
        start, end = window_bounds(rule.window, at)
        counter = connection.execute(
            _SQL_QUOTA, (tenant_id, pool, rule.name, start, end)
        ).fetchone()
        return {
            "pool": pool,
            "rule": rule.name,
            "window": rule.window.kind,
            "start": start,
            "end": end,
            "limit": rule.limit,
            **counter,
            "remaining": max(Decimal(0), rule.limit - counter["units"]),
            "remaining_is_estimate": True,
            "observed_at": at,
        }

    def quotas(self, principal, at=None):
        """Return current quota counters; incomplete source coverage stays explicit."""
        require_admin(principal)
        at = at or datetime.now(UTC)
        with self.db.tenant(principal.tenant_id) as connection:
            return self._quotas(connection, principal.tenant_id, at)

    def _quotas(self, connection, tenant_id, at, notify=False):
        result = []
        for row in connection.execute(_SQL_POOLS, (tenant_id, at)).fetchall():
            plan = ApiPlan.model_validate(row["plan"])
            for rule in plan.quota_rules:
                state = self.quota_state(connection, tenant_id, row["pool"], rule, at)
                result.append(state)
                if notify:
                    self._thresholds(connection, tenant_id, rule, state)
        return result

    def _thresholds(self, connection, tenant_id, rule, state):
        # Rolling alerts use elapsed-window buckets so repeated worker passes do not spam.
        bucket = (
            int(state["observed_at"].timestamp()) // rule.window.seconds
            if rule.window.kind == "rolling"
            else state["start"].isoformat()
        )
        for threshold in rule.thresholds:
            if state["units"] * 100 >= rule.limit * threshold:
                key = f"quota:{state['pool']}:{rule.name}:{bucket}:{threshold}"
                evidence = {**state, "threshold": threshold}
                emit_alert(connection, tenant_id, key, "quota.threshold", evidence)

    def tick(self, tenant_id, at):
        """Evaluate thresholds idempotently; durable unique keys tolerate overlapping workers."""
        with self.db.tenant(tenant_id) as connection:
            self._quotas(connection, tenant_id, at, notify=True)

    def charges(self, principal):
        """Return account-level fixed fees separately from app-attributed request costs."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_FEES, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()

    def alerts(self, principal):
        """List deduplicated threshold evidence for administrators."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_ALERTS, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()

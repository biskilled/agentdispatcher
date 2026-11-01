"""Observe external schedules and budgets using durable, idempotent PostgreSQL jobs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, Field, model_validator

from dispatcher.accounting import audit, emit_alert
from dispatcher.auth import require_admin
from dispatcher.contracts import Contract, JobEvent, Window
from dispatcher.pricing import window_bounds

_TABLES = {"schedules": "mng_schedules", "budgets": "mng_budgets"}
_SQL_GET = {
    kind: f"SELECT revision,config FROM {table} WHERE tenant_id=%s AND id=%s FOR UPDATE"
    for kind, table in _TABLES.items()
}
_SQL_LIST = {
    kind: f"SELECT id,revision,config FROM {table} WHERE tenant_id=%s ORDER BY id"
    for kind, table in _TABLES.items()
}
_SQL_PUT = {
    kind: f"""
INSERT INTO {table}(tenant_id,id,config,revision) VALUES(%s,%s,%s,1)
ON CONFLICT(tenant_id,id) DO UPDATE SET config=EXCLUDED.config,revision={table}.revision+1
WHERE {table}.revision=%s RETURNING revision
"""
    for kind, table in _TABLES.items()
}
_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_SCHEDULE = "SELECT config FROM mng_schedules WHERE tenant_id=%s AND id=%s"
_SQL_LEASE = """
INSERT INTO mng_worker_leases(tenant_id,task,owner,lease_until)
VALUES(%s,%s,%s,%s + %s * interval '1 second')
ON CONFLICT(tenant_id,task) DO UPDATE SET owner=EXCLUDED.owner,lease_until=EXCLUDED.lease_until
WHERE mng_worker_leases.lease_until<=%s RETURNING owner
"""
_SQL_RELEASE = """
UPDATE mng_worker_leases SET lease_until=%s,completed_at=%s
WHERE tenant_id=%s AND task=%s AND owner=%s
"""
_SQL_CURSOR = (
    "SELECT max(scheduled_for) latest FROM mem_expected_runs WHERE tenant_id=%s AND schedule_id=%s"
)
_SQL_EXPECTED = """
INSERT INTO mem_expected_runs(tenant_id,schedule_id,scheduled_for,checked_at)
VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING
"""
_SQL_HEALTH = """
SELECT e.schedule_id,e.scheduled_for,s.config->>'name' name,
s.config->>'app' app,count(j.run_id) observed_runs,
CASE WHEN count(j.run_id)=0 THEN 'missed'
 WHEN bool_or(j.state='running' AND j.stale) THEN 'stuck'
 WHEN bool_or(j.state='running') THEN 'running'
 WHEN bool_or(j.state='failed') THEN 'failed'
 WHEN bool_or(j.state='completed') THEN 'completed' ELSE 'cancelled' END state
FROM mem_expected_runs e JOIN mng_schedules s ON(s.tenant_id,s.id)=(e.tenant_id,e.schedule_id)
LEFT JOIN mem_job_runs j ON(j.tenant_id,j.schedule_id,j.scheduled_for)=
(e.tenant_id,e.schedule_id,e.scheduled_for)
WHERE e.tenant_id=%s GROUP BY e.schedule_id,e.scheduled_for,s.config
ORDER BY e.scheduled_for DESC LIMIT %s
"""
_SQL_SPEND = """
SELECT coalesce(sum(cost),0) amount,count(*) FILTER(WHERE cost IS NULL) unknown_events
FROM mem_usage WHERE tenant_id=%s AND occurred_at>=%s AND occurred_at<%s
AND (currency=%s OR currency IS NULL) AND (%s::text[] IS NULL OR app=ANY(%s::text[]))
"""
_SQL_FEES = """
SELECT coalesce(sum(amount),0) amount FROM mem_period_charges WHERE tenant_id=%s
AND period_start>=%s AND period_start<%s AND currency=%s
"""
_SQL_ADJUSTMENTS = """
SELECT coalesce(sum(a.amount),0) amount FROM mem_adjustments a JOIN mem_usage u
ON(u.tenant_id,u.event_id)=(a.tenant_id,a.event_id)
WHERE a.tenant_id=%s AND a.created_at>=%s AND a.created_at<%s AND a.currency=%s
AND (%s::text[] IS NULL OR u.app=ANY(%s::text[]))
"""


class Schedule(Contract):
    """An expected cadence; Dispatcher observes it and never executes the business task."""

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    name: str = Field(min_length=1, max_length=150)
    app: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=50)
    first_expected: AwareDatetime
    cadence: Window
    grace_seconds: int = Field(default=300, ge=0)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_cadence(self):
        """Reject rolling schedules, whose moving origin has no expected occurrence."""
        if self.cadence.kind == "rolling":
            raise ValueError("Use a fixed or calendar schedule cadence")
        if window_bounds(self.cadence, self.first_expected)[0] != self.first_expected:
            raise ValueError("first_expected must match the cadence's reset boundary")
        return self


class Budget(Contract):
    """Currency-specific monitoring threshold, optionally limited to selected apps."""

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    window: Window
    apps: list[str] | None = Field(default=None, max_length=100)
    thresholds: list[int] = Field(default_factory=lambda: [80, 100], min_length=1, max_length=100)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_thresholds(self):
        """Require meaningful crossing percentages and stable billing periods."""
        if any(t < 1 or t > 100 for t in self.thresholds):
            raise ValueError("Budget thresholds must be 1–100 percent")
        if self.window.kind == "rolling":
            raise ValueError("Budget periods use fixed or calendar windows")
        return self


class Operations:
    """Keep monitoring tasks restart-safe and tenant-scoped without an external queue service."""

    def __init__(self, db):
        self.db = db
        self.owner = uuid4()

    def list(self, principal, kind):
        """Read administrator-owned monitoring configuration."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(_SQL_LIST[kind], (principal.tenant_id,)).fetchall()

    def put(self, principal, kind, config, revision):
        """Publish a validated configuration revision with atomic conflict checks and audit."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            connection.execute(_SQL_LOCK, (f"{principal.tenant_id}:{kind}:{config.id}",))
            before = connection.execute(_SQL_GET[kind], (principal.tenant_id, config.id)).fetchone()
            if (before["revision"] if before else 0) != revision:
                raise HTTPException(409, "Configuration changed; reload before saving")
            payload = config.model_dump(mode="json")
            result = connection.execute(
                _SQL_PUT[kind], (principal.tenant_id, config.id, Jsonb(payload), revision)
            ).fetchone()
            audit(
                connection,
                principal,
                kind + ":" + config.id,
                "config.saved",
                before["config"] if before else None,
                payload,
            )
            return result

    def validate_run(self, connection, principal, event: JobEvent):
        """Only the configured app/environment may report a registered schedule occurrence."""
        if event.schedule_id is None:
            return
        row = connection.execute(_SQL_SCHEDULE, (principal.tenant_id, event.schedule_id)).fetchone()
        if not row:
            raise HTTPException(422, "Unknown schedule")
        schedule = Schedule.model_validate(row["config"])
        if (schedule.app, schedule.environment) != (principal.app, principal.environment):
            raise HTTPException(403, "Schedule is outside the service scope")
        if (
            event.scheduled_for < schedule.first_expected
            or window_bounds(schedule.cadence, event.scheduled_for)[0] != event.scheduled_for
        ):
            raise HTTPException(422, "Run does not match an expected schedule occurrence")

    def tick(self, tenant_id, at=None):
        """Claim a durable monitoring lease; repeated execution produces no duplicate evidence."""
        at = at or datetime.now(UTC)
        task = "schedules-and-budgets"
        with self.db.tenant(tenant_id) as connection:
            row = connection.execute(
                _SQL_LEASE,
                (tenant_id, task, self.owner, at, self.db.settings.worker_lease_seconds, at),
            ).fetchone()
        if not row:
            return False
        with self.db.tenant(tenant_id) as connection:
            for row in connection.execute(_SQL_LIST["schedules"], (tenant_id,)).fetchall():
                self._schedule(connection, tenant_id, Schedule.model_validate(row["config"]), at)
            for row in connection.execute(_SQL_LIST["budgets"], (tenant_id,)).fetchall():
                budget = Budget.model_validate(row["config"])
                if budget.enabled:
                    state = self._budget(connection, tenant_id, budget, at)
                    for threshold in budget.thresholds:
                        if state["known_amount"] * 100 >= budget.amount * threshold:
                            key = f"budget:{budget.id}:{state['start'].isoformat()}:{threshold}"
                            emit_alert(
                                connection,
                                tenant_id,
                                key,
                                "budget.threshold",
                                {**state, "threshold": threshold},
                            )
            connection.execute(_SQL_RELEASE, (at, at, tenant_id, task, self.owner))
        return True

    def _schedule(self, connection, tenant_id, schedule, at):
        if not schedule.enabled:
            return
        latest = connection.execute(_SQL_CURSOR, (tenant_id, schedule.id)).fetchone()["latest"]
        cursor = window_bounds(schedule.cadence, latest)[1] if latest else schedule.first_expected
        for _ in range(self.db.settings.schedule_catchup_limit):
            if cursor + timedelta(seconds=schedule.grace_seconds) > at:
                break
            connection.execute(_SQL_EXPECTED, (tenant_id, schedule.id, cursor, at))
            cursor = window_bounds(schedule.cadence, cursor)[1]

    def health(self, principal):
        """Compute provisional missed states from expected occurrences and late run evidence."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_HEALTH, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()

    def budgets(self, principal, at=None):
        """Report known costs and uncertainty; account fees remain outside app allocations."""
        require_admin(principal)
        at = at or datetime.now(UTC)
        with self.db.tenant(principal.tenant_id) as connection:
            return [
                self._budget(
                    connection, principal.tenant_id, Budget.model_validate(row["config"]), at
                )
                for row in connection.execute(
                    _SQL_LIST["budgets"], (principal.tenant_id,)
                ).fetchall()
            ]

    def _budget(self, connection, tenant_id, budget, at):
        start, end = window_bounds(budget.window, at)
        args = (tenant_id, start, end, budget.currency, budget.apps, budget.apps)
        result = connection.execute(_SQL_SPEND, args).fetchone()
        fee = (
            connection.execute(_SQL_FEES, args[:4]).fetchone()["amount"]
            if budget.apps is None
            else Decimal(0)
        )
        adjustments = connection.execute(_SQL_ADJUSTMENTS, args).fetchone()["amount"]
        return {
            "id": budget.id,
            "start": start,
            "end": end,
            "currency": budget.currency,
            "limit": budget.amount,
            "known_amount": result["amount"] + fee + adjustments,
            "fixed_fees": fee,
            "adjustments": adjustments,
            "unknown_events": result["unknown_events"],
        }

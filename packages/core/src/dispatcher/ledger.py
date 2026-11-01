"""Shared accounting and job persistence; only authenticated scope reaches this module."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from dispatcher.accounting import Accounting, audit
from dispatcher.auth import require_admin, require_usage_reader, usage_scope
from dispatcher.contracts import ApiPlan, JobEvent, Principal, UsageEvent
from dispatcher.db import Database
from dispatcher.operations import Operations
from dispatcher.pricing import calculate_price
from dispatcher.reporting import Reporter, UsageFilter

_SQL_PLAN_INSERT = """
INSERT INTO mng_api_plans(tenant_id,id,api_id,effective_at,plan) VALUES (%s,%s,%s,%s,%s)
ON CONFLICT (tenant_id,api_id,effective_at) DO NOTHING RETURNING id
"""
_SQL_PLANS = """
SELECT id,api_id,effective_at,plan FROM mng_api_plans
WHERE tenant_id=%s ORDER BY effective_at DESC
"""
_SQL_PRICE = """
SELECT id,plan FROM mng_api_plans WHERE tenant_id=%s AND api_id=%s AND effective_at <= %s
ORDER BY effective_at DESC LIMIT 1
"""
_SQL_INSERT = """
INSERT INTO mem_usage(tenant_id,event_id,service_id,attempt_id,occurred_at,app,environment,
resource_kind,provider,model,api_id,job_run_id,status,payload,evidence_hash,cost,currency,
cost_kind,plan_id,verified_user_id)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT DO NOTHING RETURNING event_id
"""
_SQL_EXISTING = """
SELECT evidence_hash,verified_user_id FROM mem_usage WHERE tenant_id=%s
AND (event_id=%s OR (app=%s AND environment=%s AND attempt_id=%s))
"""
_SQL_APP_VISIBLE = "AND (%s OR app=ANY(%s::text[]))"
_SQL_JOB = """
INSERT INTO mem_job_runs(tenant_id,run_id,service_id,app,environment,name,state,
occurred_at,trace_id,started_at,schedule_id,scheduled_for)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (tenant_id,run_id) DO UPDATE SET state=EXCLUDED.state,
occurred_at=EXCLUDED.occurred_at,received_at=now(),stale=false
WHERE mem_job_runs.app=EXCLUDED.app AND mem_job_runs.environment=EXCLUDED.environment
AND mem_job_runs.service_id=EXCLUDED.service_id
AND mem_job_runs.schedule_id IS NOT DISTINCT FROM EXCLUDED.schedule_id
AND mem_job_runs.scheduled_for IS NOT DISTINCT FROM EXCLUDED.scheduled_for
AND mem_job_runs.occurred_at <= EXCLUDED.occurred_at
AND (mem_job_runs.state='running' OR mem_job_runs.state=EXCLUDED.state)
RETURNING run_id
"""
_SQL_JOBS = (
    """
SELECT run_id,app,environment,name,state,occurred_at,received_at,trace_id,stale,
started_at,schedule_id,scheduled_for
FROM mem_job_runs WHERE tenant_id=%s
"""
    + _SQL_APP_VISIBLE
    + " ORDER BY occurred_at DESC LIMIT %s"
)
_SQL_STALE = """
UPDATE mem_job_runs SET stale=true WHERE tenant_id=%s AND state='running'
AND received_at < now() - %s * interval '1 second' AND NOT stale
"""
_SQL_HEARTBEAT = """
INSERT INTO mem_worker_health(tenant_id,last_seen) VALUES (%s,now())
ON CONFLICT (tenant_id) DO UPDATE SET last_seen=now()
"""
_SQL_TENANTS = "SELECT id FROM mng_tenants ORDER BY id"
_SQL_INGEST_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"


def validate_scope(principal: Principal, event) -> None:
    """Prevent a key for one app/environment from submitting another app's records."""
    if principal.role != "service":
        raise HTTPException(403, "SDK key required")
    if (event.app, event.environment) != (principal.app, principal.environment):
        raise HTTPException(403, "Event is outside the SDK key scope")
    if getattr(event, "tenant_id", None) not in (None, principal.tenant_id):
        raise HTTPException(403, "Event tenant does not match SDK key")


class Ledger:
    """Use one canonical event store and pricing implementation for all resource kinds."""

    def __init__(self, db: Database):
        self.db = db
        self.accounting = Accounting(db)
        self.operations = Operations(db)

    def ingest(self, principal: Principal, events: list[UsageEvent]) -> dict:
        """Persist a batch atomically, rejecting altered replays and scope mismatches."""
        for event in events:
            validate_scope(principal, event)
        inserted = 0
        with self.db.tenant(principal.tenant_id) as connection:
            # Atomic batches can span pools; a consistent outer lock prevents lock-order deadlocks.
            connection.execute(_SQL_INGEST_LOCK, (f"{principal.tenant_id}:ingest",))
            for event in events:
                inserted += self._insert(connection, principal, event)
        return {"inserted": inserted, "duplicates": len(events) - inserted}

    def _insert(self, connection, principal: Principal, event: UsageEvent) -> int:
        canonical = event.model_copy(update={"tenant_id": principal.tenant_id})
        payload = canonical.model_dump(mode="json")
        # New optional evidence fields must not change hashes for pre-upgrade replays.
        omitted = {"reported_cost", "reported_currency"} if event.reported_cost is None else set()
        digest = hashlib.sha256(canonical.model_dump_json(exclude=omitted).encode()).hexdigest()
        row = connection.execute(
            _SQL_PRICE, (principal.tenant_id, event.api_id, event.occurred_at)
        ).fetchone()
        plan = ApiPlan.model_validate(row["plan"]) if row else None
        context = None
        if plan:
            context, price = self.accounting.prepare(connection, principal, plan, event)
        else:
            price = calculate_price(None, event)
        cost, currency, kind = price
        if event.reported_cost is not None:
            cost, currency = event.reported_cost, event.reported_currency
            kind = "gateway_calculated" if principal.purpose == "gateway" else "app_estimate"
        args = (
            principal.tenant_id,
            event.event_id,
            principal.subject_id,
            event.attempt_id,
            event.occurred_at,
            event.app,
            event.environment,
            event.resource_kind,
            event.provider,
            event.model,
            event.api_id,
            event.job_run_id,
            event.status,
            Jsonb(payload),
            digest,
            cost,
            currency,
            kind,
            row["id"] if row else None,
            principal.verified_user_id,
        )
        if connection.execute(_SQL_INSERT, args).fetchone():
            if plan:
                self.accounting.record(connection, principal, row["id"], plan, event, context)
            return 1
        existing = connection.execute(
            _SQL_EXISTING,
            (principal.tenant_id, event.event_id, event.app, event.environment, event.attempt_id),
        ).fetchall()
        if not existing or any(
            item["evidence_hash"] != digest
            or item["verified_user_id"] != principal.verified_user_id
            for item in existing
        ):
            raise HTTPException(409, "Event or attempt ID already exists with different evidence")
        return 0

    def overview(self, principal: Principal, app: str | None = None) -> dict:
        """Return authorised totals through the shared reporting model."""
        return Reporter(self.db).overview(principal, UsageFilter(app_name=app))

    def events(self, principal: Principal, offset: int = 0, app: str | None = None) -> list:
        """Return one authorised event page through the shared reporting model."""
        return Reporter(self.db).events(principal, UsageFilter(app_name=app, offset=offset))

    def plans(self, principal: Principal) -> list:
        """Read the tenant's versioned catalog."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(_SQL_PLANS, (principal.tenant_id,)).fetchall()

    def add_plan(self, principal: Principal, plan: ApiPlan) -> dict:
        """Append a plan version; previously priced events retain their original evidence."""
        require_admin(principal)
        plan_id = uuid4()
        with self.db.tenant(principal.tenant_id) as connection:
            row = connection.execute(
                _SQL_PLAN_INSERT,
                (
                    principal.tenant_id,
                    plan_id,
                    plan.api_id,
                    plan.effective_at,
                    Jsonb(plan.model_dump(mode="json")),
                ),
            ).fetchone()
            if row:
                audit(
                    connection,
                    principal,
                    "plan:" + str(plan_id),
                    "plan.published",
                    None,
                    plan.model_dump(mode="json"),
                )
        if row is None:
            raise HTTPException(409, "A plan already exists for that API and effective time")
        return {"id": plan_id}

    def job(self, principal: Principal, event: JobEvent) -> None:
        """Record a monotonic run transition; late running events cannot reopen a terminal run."""
        validate_scope(principal, event)
        with self.db.tenant(principal.tenant_id) as connection:
            self.operations.validate_run(connection, principal, event)
            row = connection.execute(
                _SQL_JOB,
                (
                    principal.tenant_id,
                    event.run_id,
                    principal.subject_id,
                    event.app,
                    event.environment,
                    event.name,
                    event.state,
                    event.occurred_at,
                    event.trace_id,
                    event.occurred_at,
                    event.schedule_id,
                    event.scheduled_for,
                ),
            ).fetchone()
            if row is None:
                raise HTTPException(409, "Stale, conflicting or out-of-scope run update")

    def jobs(self, principal: Principal) -> list:
        """Return recent run health for the selected tenant."""
        require_usage_reader(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_JOBS,
                (principal.tenant_id, *usage_scope(principal)[:2], self.db.settings.page_size),
            ).fetchall()

    def tick(self) -> int:
        """Visit tenants independently; mark stale runs without inventing a failure outcome."""
        with self.db.auth() as connection:
            tenants = connection.execute(_SQL_TENANTS).fetchall()
        for tenant in tenants:
            with self.db.tenant(tenant["id"]) as connection:
                connection.execute(
                    _SQL_STALE, (tenant["id"], self.db.settings.heartbeat_grace_seconds)
                )
                connection.execute(_SQL_HEARTBEAT, (tenant["id"],))
            self.accounting.tick(tenant["id"], datetime.now(UTC))
            self.operations.tick(tenant["id"])
        return len(tenants)

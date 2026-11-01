"""Shared accounting and job persistence; only authenticated scope reaches this module."""

import hashlib
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from dispatcher.auth import require_admin, require_usage_reader
from dispatcher.contracts import ApiPlan, JobEvent, Principal, UsageEvent
from dispatcher.db import Database

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
cost_kind,plan_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT DO NOTHING RETURNING event_id
"""
_SQL_EXISTING = """
SELECT evidence_hash FROM mem_usage WHERE tenant_id=%s
AND (event_id=%s OR (app=%s AND environment=%s AND attempt_id=%s))
"""
_SQL_EVENTS = """
SELECT event_id,occurred_at,app,environment,resource_kind,provider,model,api_id,status,
cost,currency,cost_kind,job_run_id,payload FROM mem_usage WHERE tenant_id=%s
AND (%s::text IS NULL OR app=%s) ORDER BY occurred_at DESC,event_id LIMIT %s OFFSET %s
"""
_SQL_TOTALS = """
SELECT currency,cost_kind,count(*) AS attempts,sum(cost) AS cost
FROM mem_usage WHERE tenant_id=%s AND (%s::text IS NULL OR app=%s)
GROUP BY currency,cost_kind ORDER BY currency,cost_kind
"""
_SQL_COUNTS = """
SELECT count(*) AS attempts, count(*) FILTER (WHERE cost IS NULL) AS unknown_cost,
count(*) FILTER (WHERE status IN ('error','timeout')) AS failures,
max(created_at) AS last_received_at FROM mem_usage WHERE tenant_id=%s
AND (%s::text IS NULL OR app=%s)
"""
_SQL_BREAKDOWN = """
SELECT app,provider,resource_kind,currency,cost_kind,count(*) AS attempts,sum(cost) AS cost
FROM mem_usage WHERE tenant_id=%s GROUP BY app,provider,resource_kind,currency,cost_kind
ORDER BY attempts DESC
"""
_SQL_JOB = """
INSERT INTO mem_job_runs(tenant_id,run_id,service_id,app,environment,name,state,
occurred_at,trace_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (tenant_id,run_id) DO UPDATE SET state=EXCLUDED.state,
occurred_at=EXCLUDED.occurred_at,received_at=now(),stale=false
WHERE mem_job_runs.app=EXCLUDED.app AND mem_job_runs.environment=EXCLUDED.environment
AND mem_job_runs.service_id=EXCLUDED.service_id
AND mem_job_runs.occurred_at <= EXCLUDED.occurred_at
AND (mem_job_runs.state='running' OR mem_job_runs.state=EXCLUDED.state)
RETURNING run_id
"""
_SQL_JOBS = """
SELECT run_id,app,environment,name,state,occurred_at,received_at,trace_id,stale
FROM mem_job_runs WHERE tenant_id=%s ORDER BY occurred_at DESC LIMIT %s
"""
_SQL_STALE = """
UPDATE mem_job_runs SET stale=true WHERE tenant_id=%s AND state='running'
AND received_at < now() - %s * interval '1 second' AND NOT stale
"""
_SQL_HEARTBEAT = """
INSERT INTO mem_worker_health(tenant_id,last_seen) VALUES (%s,now())
ON CONFLICT (tenant_id) DO UPDATE SET last_seen=now()
"""
_SQL_TENANTS = "SELECT id FROM mng_tenants ORDER BY id"


def validate_scope(principal: Principal, event) -> None:
    """Prevent a key for one app/environment from submitting another app's records."""
    if principal.role != "service":
        raise HTTPException(403, "SDK key required")
    if (event.app, event.environment) != (principal.app, principal.environment):
        raise HTTPException(403, "Event is outside the SDK key scope")
    if getattr(event, "tenant_id", None) not in (None, principal.tenant_id):
        raise HTTPException(403, "Event tenant does not match SDK key")


def calculate_price(plan: ApiPlan | None, event: UsageEvent) -> tuple:
    """Calculate configured cost only; unknown rules and timeouts remain unknown."""
    if plan is None or plan.pricing == "unknown":
        return None, None if plan is None else plan.currency, "unknown"
    if plan.pricing == "free":
        return Decimal(0), plan.currency, "configured_free"
    if event.status == "timeout" or event.status_code is None:
        return None, plan.currency, "unknown"
    billable = event.status_code in plan.charge_statuses
    cost = event.units * plan.unit_price if billable else Decimal(0)
    return cost, plan.currency, "calculated"


class Ledger:
    """Use one canonical event store and pricing implementation for all resource kinds."""

    def __init__(self, db: Database):
        self.db = db

    def ingest(self, principal: Principal, events: list[UsageEvent]) -> dict:
        """Persist a batch atomically, rejecting altered replays and scope mismatches."""
        for event in events:
            validate_scope(principal, event)
        inserted = 0
        with self.db.tenant(principal.tenant_id) as connection:
            for event in events:
                inserted += self._insert(connection, principal, event)
        return {"inserted": inserted, "duplicates": len(events) - inserted}

    def _insert(self, connection, principal: Principal, event: UsageEvent) -> int:
        canonical = event.model_copy(update={"tenant_id": principal.tenant_id})
        payload = canonical.model_dump(mode="json")
        digest = hashlib.sha256(canonical.model_dump_json().encode()).hexdigest()
        row = connection.execute(
            _SQL_PRICE, (principal.tenant_id, event.api_id, event.occurred_at)
        ).fetchone()
        plan = ApiPlan.model_validate(row["plan"]) if row else None
        cost, currency, kind = calculate_price(plan, event)
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
        )
        if connection.execute(_SQL_INSERT, args).fetchone():
            return 1
        existing = connection.execute(
            _SQL_EXISTING,
            (principal.tenant_id, event.event_id, event.app, event.environment, event.attempt_id),
        ).fetchall()
        if not existing or any(item["evidence_hash"] != digest for item in existing):
            raise HTTPException(409, "Event or attempt ID already exists with different evidence")
        return 0

    def overview(self, principal: Principal, app: str | None = None) -> dict:
        """Return totals by currency and provenance; unknown is never converted to zero."""
        require_usage_reader(principal)
        args = (principal.tenant_id, app, app)
        with self.db.tenant(principal.tenant_id) as connection:
            return {
                "counts": connection.execute(_SQL_COUNTS, args).fetchone(),
                "totals": connection.execute(_SQL_TOTALS, args).fetchall(),
                "breakdown": connection.execute(_SQL_BREAKDOWN, (principal.tenant_id,)).fetchall(),
            }

    def events(self, principal: Principal, offset: int = 0, app: str | None = None) -> list:
        """Read a bounded page; SDK actor IDs are explicitly app-reported."""
        require_usage_reader(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            rows = connection.execute(
                _SQL_EVENTS, (principal.tenant_id, app, app, self.db.settings.page_size, offset)
            ).fetchall()
        for row in rows:
            row["user_attribution"] = "app_reported" if row["payload"]["user_id"] else "service"
        return rows

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
        if row is None:
            raise HTTPException(409, "A plan already exists for that API and effective time")
        return {"id": plan_id}

    def job(self, principal: Principal, event: JobEvent) -> None:
        """Record a monotonic run transition; late running events cannot reopen a terminal run."""
        validate_scope(principal, event)
        with self.db.tenant(principal.tenant_id) as connection:
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
                ),
            ).fetchone()
            if row is None:
                raise HTTPException(409, "Stale, conflicting or out-of-scope run update")

    def jobs(self, principal: Principal) -> list:
        """Return recent run health for the selected tenant."""
        require_usage_reader(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_JOBS, (principal.tenant_id, self.db.settings.page_size)
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
        return len(tenants)

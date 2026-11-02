"""Tenant-controlled attribution expiry preserves financial evidence and replay protection."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field

from dispatcher.accounting import audit
from dispatcher.auth import require_admin
from dispatcher.contracts import Contract, Principal

_SQL_GET = "SELECT attribution_days,revision FROM mng_retention_policy WHERE tenant_id=%s"
_SQL_SAVE = """
INSERT INTO mng_retention_policy(tenant_id,attribution_days,revision,updated_by)
VALUES(%s,%s,1,%s) ON CONFLICT(tenant_id) DO UPDATE SET
attribution_days=EXCLUDED.attribution_days,revision=mng_retention_policy.revision+1,
updated_by=EXCLUDED.updated_by,updated_at=now() RETURNING revision
"""
_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_REDACT = {
    table: f"""
WITH expired AS (
 SELECT event_id FROM {table} WHERE tenant_id=%s AND {timestamp}<%s
 AND attribution_expired_at IS NULL ORDER BY {timestamp},event_id
 LIMIT %s FOR UPDATE SKIP LOCKED
)
UPDATE {table} SET payload=payload || %s::jsonb,verified_user_id=NULL,
{extra} attribution_expired_at=%s FROM expired
WHERE {table}.tenant_id=%s AND {table}.event_id=expired.event_id
"""
    for table, timestamp, extra in (
        ("mem_usage", "occurred_at", "job_run_id=NULL,"),
        ("mem_observations", "created_at", ""),
    )
}
_REDACTED = dict.fromkeys(
    (
        "user_id",
        "project",
        "work_item",
        "pipeline_role",
        "session_id",
        "trace_id",
        "job_run_id",
        "config_version",
    )
)


class RetentionPolicy(Contract):
    """No automatic expiry unless a tenant administrator explicitly enables a horizon."""

    attribution_days: int | None = Field(default=None, ge=1, le=36500)
    revision: int = Field(ge=0)


class Retention:
    """Erase old attribution in bounded worker batches, retaining charges and idempotency hashes."""

    def __init__(self, db):
        self.db = db

    def policy(self, principal):
        """Read the tenant's explicit policy; absence means disabled."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(_SQL_GET, (principal.tenant_id,)).fetchone() or {
                "attribution_days": None,
                "revision": 0,
            }

    def save(self, principal, policy):
        """Audit optimistic changes; disabling does not restore already expired attribution."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            connection.execute(_SQL_LOCK, ("retention:" + str(principal.tenant_id),))
            previous = connection.execute(_SQL_GET, (principal.tenant_id,)).fetchone()
            if policy.revision != (previous["revision"] if previous else 0):
                raise HTTPException(409, "Retention policy changed; reload before saving")
            saved = connection.execute(
                _SQL_SAVE, (principal.tenant_id, policy.attribution_days, principal.subject_id)
            ).fetchone()
            result = {"attribution_days": policy.attribution_days, **saved}
            audit(connection, principal, "retention", "retention.policy", previous, result)
            return result

    def tick(self, connection, tenant_id, now):
        """Use the worker's tenant transaction and row locks to avoid overlapping batches."""
        policy = connection.execute(_SQL_GET, (tenant_id,)).fetchone()
        if not policy or policy["attribution_days"] is None:
            return {}
        cutoff = now - timedelta(days=policy["attribution_days"])
        counts = {
            table: connection.execute(
                statement,
                (
                    tenant_id,
                    cutoff,
                    self.db.settings.retention_batch_rows,
                    Jsonb(_REDACTED),
                    now,
                    tenant_id,
                ),
            ).rowcount
            for table, statement in _SQL_REDACT.items()
        }
        if any(counts.values()):
            audit(
                connection,
                Principal(tenant_id=tenant_id, subject_id=tenant_id, role="service"),
                "retention",
                "retention.expired",
                None,
                {"cutoff": cutoff.isoformat(), "counts": counts, "revision": policy["revision"]},
            )
        return counts


def routes(db, human):
    """Expose administrator settings; worker processing shares the retention service."""
    router = APIRouter(prefix="/api/retention")
    retention = Retention(db)

    @router.get("")
    def get_policy(principal=Depends(human)):
        """Read the current tenant's attribution horizon."""
        return retention.policy(principal)

    @router.put("")
    def put_policy(body: RetentionPolicy, principal=Depends(human)):
        """Enable, change or disable future attribution expiry."""
        return retention.save(principal, body)

    return router

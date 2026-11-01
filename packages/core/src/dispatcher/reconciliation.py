"""Imported provider evidence is compared with, never added to, observed request totals."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, model_validator

from dispatcher.accounting import audit
from dispatcher.auth import require_admin
from dispatcher.contracts import Contract

_SQL_SNAPSHOT = """
INSERT INTO mem_provider_snapshots(tenant_id,id,pool,provider_ref,period_start,period_end,
amount,currency,units,observed_at,source_note) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT(tenant_id,pool,provider_ref) DO NOTHING RETURNING id
"""
_SQL_EXISTING = """
SELECT * FROM mem_provider_snapshots WHERE tenant_id=%s AND pool=%s AND provider_ref=%s
"""
_SQL_SNAPSHOTS = """
SELECT * FROM mem_provider_snapshots WHERE tenant_id=%s ORDER BY observed_at DESC LIMIT %s
"""
_SQL_LOCAL = """
SELECT coalesce(sum(u.cost) FILTER(WHERE u.currency=%s),0) amount,
count(*) FILTER(WHERE u.cost IS NULL) unknown_events,coalesce(sum(r.units),0) units
FROM mem_usage_ratings r JOIN mem_usage u ON(u.tenant_id,u.event_id)=(r.tenant_id,r.event_id)
WHERE r.tenant_id=%s AND r.pool=%s AND r.occurred_at>=%s AND r.occurred_at<%s
"""
_SQL_FEES = """
SELECT coalesce(sum(amount),0) amount FROM mem_period_charges WHERE tenant_id=%s AND pool=%s
AND period_start>=%s AND period_start<%s AND currency=%s
"""
_SQL_ADJUSTMENTS = """
SELECT coalesce(sum(a.amount),0) amount FROM mem_adjustments a JOIN mem_usage_ratings r
ON(r.tenant_id,r.event_id)=(a.tenant_id,a.event_id)
WHERE a.tenant_id=%s AND r.pool=%s AND a.created_at>=%s AND a.created_at<%s AND a.currency=%s
"""
_SQL_EVENT = "SELECT currency FROM mem_usage WHERE tenant_id=%s AND event_id=%s"
_SQL_ADJUST = """
INSERT INTO mem_adjustments(tenant_id,id,event_id,amount,currency,source_ref,reason,created_by)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,source_ref) DO NOTHING RETURNING id
"""
_SQL_ADJUST_EXISTING = "SELECT * FROM mem_adjustments WHERE tenant_id=%s AND source_ref=%s"
_SQL_ADJUST_LIST = """
SELECT id,event_id,amount,currency,source_ref,reason,created_at FROM mem_adjustments
WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s
"""


class ProviderSnapshot(Contract):
    """An administrator-imported statement or provider counter; no invoice double counting."""

    pool: str = Field(min_length=1, max_length=400)
    provider_ref: str = Field(min_length=1, max_length=150)
    period_start: AwareDatetime
    period_end: AwareDatetime
    amount: Decimal | None = Field(default=None, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    units: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    observed_at: AwareDatetime
    source_note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_evidence(self):
        """Require complete monetary evidence or units and a nonempty statement period."""
        if self.period_start >= self.period_end:
            raise ValueError("Statement period must have positive duration")
        if (self.amount is None) != (self.currency is None):
            raise ValueError("Amount and currency must be provided together")
        if self.amount is None and self.units is None:
            raise ValueError("Provider evidence requires an amount or units")
        return self


class Adjustment(Contract):
    """A signed refund/correction linked to original evidence and an immutable source reference."""

    event_id: UUID
    amount: Decimal = Field(allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_ref: str = Field(min_length=1, max_length=150)
    reason: str = Field(min_length=1, max_length=500)


class Reconciliation:
    """Preserve original calculations and append explicit, audited evidence separately."""

    def __init__(self, db):
        self.db = db

    def import_snapshot(self, principal, body: ProviderSnapshot):
        """Import idempotently; changed evidence under an existing source ID is a conflict."""
        require_admin(principal)
        data = body.model_dump()
        with self.db.tenant(principal.tenant_id) as connection:
            row = connection.execute(
                _SQL_SNAPSHOT, (principal.tenant_id, uuid4(), *data.values())
            ).fetchone()
            if row:
                audit(
                    connection,
                    principal,
                    "snapshot:" + str(row["id"]),
                    "snapshot.imported",
                    None,
                    body.model_dump(mode="json"),
                )
            else:
                row = connection.execute(
                    _SQL_EXISTING, (principal.tenant_id, body.pool, body.provider_ref)
                ).fetchone()
                if any(row[key] != value for key, value in data.items()):
                    raise HTTPException(409, "Provider reference already has different evidence")
            return {"id": row["id"]}

    def reports(self, principal, at=None):
        """Show observed-versus-reported drift, unknown costs and provider evidence age."""
        require_admin(principal)
        at = at or datetime.now(UTC)
        with self.db.tenant(principal.tenant_id) as connection:
            rows = connection.execute(
                _SQL_SNAPSHOTS, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()
            for row in rows:
                args = (principal.tenant_id, row["pool"], row["period_start"], row["period_end"])
                local = connection.execute(_SQL_LOCAL, (row["currency"], *args)).fetchone()
                fees = connection.execute(_SQL_FEES, (*args, row["currency"])).fetchone()["amount"]
                adjustments = connection.execute(
                    _SQL_ADJUSTMENTS, (*args, row["currency"])
                ).fetchone()["amount"]
                amount = local["amount"] + fees + adjustments
                row.update(
                    observed_amount=amount if row["currency"] else None,
                    observed_units=local["units"],
                    unknown_events=local["unknown_events"],
                    drift=row["amount"] - amount if row["amount"] is not None else None,
                    stale=(at - row["observed_at"]).total_seconds()
                    > self.db.settings.snapshot_stale_seconds,
                )
            return rows

    def adjust(self, principal, body: Adjustment):
        """Append a signed correction once; never rewrite the original event price."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            event = connection.execute(_SQL_EVENT, (principal.tenant_id, body.event_id)).fetchone()
            if not event:
                raise HTTPException(404, "Original event not found")
            if event["currency"] not in (None, body.currency):
                raise HTTPException(422, "Adjustment currency must match the original event")
            row = connection.execute(
                _SQL_ADJUST,
                (
                    principal.tenant_id,
                    uuid4(),
                    body.event_id,
                    body.amount,
                    body.currency,
                    body.source_ref,
                    body.reason,
                    principal.subject_id,
                ),
            ).fetchone()
            if row:
                audit(
                    connection,
                    principal,
                    "adjustment:" + str(row["id"]),
                    "cost.adjusted",
                    None,
                    body.model_dump(mode="json"),
                )
            else:
                row = connection.execute(
                    _SQL_ADJUST_EXISTING, (principal.tenant_id, body.source_ref)
                ).fetchone()
                if any(row[key] != value for key, value in body.model_dump().items()):
                    raise HTTPException(409, "Adjustment reference already has different evidence")
            return {"id": row["id"]}

    def adjustments(self, principal):
        """Return audited corrections separately from original request costs."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_ADJUST_LIST, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()

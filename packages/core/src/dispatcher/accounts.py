"""Tenant-scoped account snapshots; quota refreshes never become billable request events."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, Field, model_validator

from dispatcher.auth import require_usage_reader, usage_scope
from dispatcher.contracts import Contract

_SQL_KEY = "SELECT source_type FROM mng_sdk_keys WHERE id=%s AND tenant_id=%s"
_SQL_UPSERT = """
INSERT INTO mem_account_snapshots(tenant_id,service_id,provider,account_key,app,environment,
verified_user_id,observed_at,snapshot) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT(tenant_id,service_id,provider,account_key) DO UPDATE SET
 observed_at=excluded.observed_at,snapshot=excluded.snapshot,received_at=now(),
 verified_user_id=excluded.verified_user_id
WHERE mem_account_snapshots.observed_at < excluded.observed_at
RETURNING provider
"""
_SQL_LIST = """
SELECT service_id,app,environment,verified_user_id,received_at,snapshot FROM mem_account_snapshots
WHERE tenant_id=%s AND (%s OR app=ANY(%s::text[]) OR verified_user_id=%s::uuid)
AND (%s::text IS NULL OR app=%s) AND (%s::text IS NULL OR provider=%s)
AND (%s::text IS NULL OR environment=%s)
AND (%s::text IS NULL OR coalesce(verified_user_id::text,snapshot->>'account')=%s)
ORDER BY app,provider,account_key LIMIT %s
"""
Name = Annotated[str, Field(min_length=1, max_length=200)]
Number = Annotated[float, Field(allow_inf_nan=False)]


class AccountWindow(Contract):
    """A provider percentage may exceed 100; missing measurements remain unknown."""

    label: Name
    used_percent: Number | None = None
    window_minutes: Annotated[int, Field(ge=0)] | None = None
    resets_at: AwareDatetime | None = None
    reset_description: Name | None = None
    quota_limit: Number | None = None
    quota_unit: Name | None = None


class AccountDetail(Contract):
    """Generic CodexBar display rows, excluding raw provider payloads and credentials."""

    label: Name
    value: str | None = Field(default=None, max_length=200)
    secondary_value: str | None = Field(default=None, max_length=200)


class AccountSnapshot(Contract):
    """One collected account state with separate source observation and collection times."""

    provider: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    account: Name
    source: Name
    version: Name | None = None
    collected_at: AwareDatetime
    observed_at: AwareDatetime | None = None
    status: Literal["ready", "error", "unavailable"]
    windows: list[AccountWindow] = Field(default_factory=list, max_length=50)
    credits_remaining: Number | None = None
    details: list[AccountDetail] = Field(default_factory=list, max_length=200)
    spend: "AccountSpend | None" = None

    @model_validator(mode="after")
    def plausible_times(self):
        """Prevent future snapshots from indefinitely suppressing later legitimate updates."""
        latest = datetime.now(UTC) + timedelta(minutes=5)
        if self.collected_at > latest or (self.observed_at and self.observed_at > latest):
            raise ValueError("Account snapshot timestamp is in the future")
        return self


class AccountSpend(Contract):
    """Provider-reported period spending, kept separate from Dispatcher calculated costs."""

    used: Number | None = None
    limit: Number | None = None
    unit: Name | None = None
    period: Name | None = None
    balance: Number | None = None
    personal_used: Number | None = None
    resets_at: AwareDatetime | None = None
    observed_at: AwareDatetime | None = None


class AccountBatch(Contract):
    """A bounded batch can contain successful and unavailable accounts from any provider."""

    snapshots: list[AccountSnapshot] = Field(min_length=1, max_length=200)


class Accounts:
    """Reuse CodexBar fetchers while enforcing Dispatcher scopes and non-additive storage."""

    def __init__(self, db):
        self.db = db

    def ingest(self, principal, batch):
        """Accept only a dedicated account-sync key; replayed or older batches cannot add cost."""
        with self.db.auth() as connection:
            key = connection.execute(
                _SQL_KEY, (principal.subject_id, principal.tenant_id)
            ).fetchone()
        if principal.role != "service" or not key or key["source_type"] != "codexbar":
            raise HTTPException(403, "A CLI account sync key is required")
        updated = 0
        with self.db.tenant(principal.tenant_id) as connection:
            for snapshot in batch.snapshots:
                account_key = hashlib.sha256(snapshot.account.encode()).hexdigest()
                row = connection.execute(
                    _SQL_UPSERT,
                    (
                        principal.tenant_id,
                        principal.subject_id,
                        snapshot.provider,
                        account_key,
                        principal.app,
                        principal.environment,
                        principal.verified_user_id,
                        snapshot.collected_at,
                        Jsonb(snapshot.model_dump(mode="json")),
                    ),
                ).fetchone()
                updated += bool(row)
        return {"updated": updated, "ignored": len(batch.snapshots) - updated}

    def list(self, principal, filters):
        """Apply dashboard app/provider/person filters to latest account states, never sum them."""
        require_usage_reader(principal)
        if filters.source not in (None, "codexbar"):
            return []
        account_fields = {"app_name", "environment", "provider", "source", "user_id"}
        controls = {"from_time", "to_time", "group_by", "offset", "include_test"}
        if any(
            value is not None
            for name, value in filters.model_dump().items()
            if name not in account_fields | controls
        ):
            # Account balances cannot truthfully be attributed to a request model, job or trace.
            return []
        with self.db.tenant(principal.tenant_id) as connection:
            rows = connection.execute(
                _SQL_LIST,
                (
                    principal.tenant_id,
                    *usage_scope(principal),
                    filters.app_name,
                    filters.app_name,
                    filters.provider,
                    filters.provider,
                    filters.environment,
                    filters.environment,
                    filters.user_id,
                    filters.user_id,
                    self.db.settings.page_size,
                ),
            ).fetchall()
        now = datetime.now(UTC)
        for row in rows:
            observed = row["snapshot"].get("observed_at")
            row["stale"] = (
                not observed
                or (now - datetime.fromisoformat(observed)).total_seconds()
                > self.db.settings.account_stale_seconds
            )
        return rows

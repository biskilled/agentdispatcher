"""One filtered read model for dashboards, drilldowns, exports and authorised tools."""

from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, Field, model_validator

from dispatcher.auth import require_usage_reader, usage_scope
from dispatcher.contracts import Contract

_FILTER_COLUMNS = {
    "app_name": "app",
    "environment": "environment",
    "provider": "provider",
    "model": "model",
    "source": "payload->>'source'",
    "user_id": "coalesce(verified_user_id::text,payload->>'user_id')",
    "session_id": "payload->>'session_id'",
    "project": "payload->>'project'",
    "work_item": "payload->>'work_item'",
    "job_run_id": "job_run_id::text",
    "config_version": "payload->>'config_version'",
    "resource_kind": "resource_kind",
    "operation_id": "payload->>'operation_id'",
    "api_id": "api_id",
}
_GROUP_COLUMNS = {**_FILTER_COLUMNS, "app": "app", "operation": "payload->>'operation'"}
_SQL_WHERE = """
WHERE tenant_id=%s AND (%s OR app=ANY(%s::text[]) OR verified_user_id=%s::uuid)
AND (%s::timestamptz IS NULL OR occurred_at >= %s)
AND (%s::timestamptz IS NULL OR occurred_at < %s)
""" + "".join(f" AND (%s::text IS NULL OR {column}=%s)" for column in _FILTER_COLUMNS.values())
_SQL_COUNTS = (
    """
SELECT count(*) attempts,count(*) FILTER(WHERE cost IS NULL) unknown_cost,
count(*) FILTER(WHERE status IN ('error','timeout')) failures,max(created_at) last_received_at,
sum((payload->>'input_tokens')::bigint) input_tokens,
sum((payload->>'output_tokens')::bigint) output_tokens,
avg((payload->>'duration_ms')::numeric) average_latency_ms FROM mem_usage
"""
    + _SQL_WHERE
)
_SQL_TOTALS = (
    """
SELECT currency,cost_kind,count(*) attempts,sum(cost) cost FROM mem_usage
"""
    + _SQL_WHERE
    + " GROUP BY currency,cost_kind ORDER BY currency,cost_kind"
)
_SQL_BREAKDOWN = (
    """
SELECT app,provider,resource_kind,currency,cost_kind,count(*) attempts,sum(cost) cost
FROM mem_usage
"""
    + _SQL_WHERE
    + " GROUP BY app,provider,resource_kind,currency,cost_kind ORDER BY attempts DESC LIMIT %s"
)
_SQL_EVENTS = (
    """
SELECT event_id,occurred_at,app,environment,resource_kind,provider,model,api_id,status,
cost,currency,cost_kind,job_run_id,payload,verified_user_id,plan_id FROM mem_usage
"""
    + _SQL_WHERE
)
_SQL_EVENT_PAGE = _SQL_EVENTS + " ORDER BY occurred_at DESC,event_id LIMIT %s OFFSET %s"
_SQL_EVENT_ONE = _SQL_EVENTS + " AND event_id=%s"
_SQL_TREND = (
    """
SELECT date_trunc('day',occurred_at AT TIME ZONE 'UTC') AS day,currency,cost_kind,
count(*) attempts,sum(cost) cost,count(*) FILTER(WHERE cost IS NULL) unknown_cost
FROM mem_usage
"""
    + _SQL_WHERE
    + " GROUP BY day,currency,cost_kind ORDER BY day DESC LIMIT %s"
)
_SQL_GROUPS = {
    key: f"SELECT {column} label,currency,cost_kind,count(*) attempts,sum(cost) cost "
    "FROM mem_usage "
    + _SQL_WHERE
    + f" GROUP BY {column},currency,cost_kind ORDER BY attempts DESC LIMIT %s"
    for key, column in _GROUP_COLUMNS.items()
}


class UsageFilter(Contract):
    """Exact-match drilldown dimensions and a half-open UTC time range."""

    from_time: AwareDatetime | None = None
    to_time: AwareDatetime | None = None
    app_name: str | None = None
    environment: str | None = None
    provider: str | None = None
    model: str | None = None
    source: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    project: str | None = None
    work_item: str | None = None
    job_run_id: str | None = None
    config_version: str | None = None
    resource_kind: str | None = None
    operation_id: str | None = None
    api_id: str | None = None
    group_by: Literal[
        "app",
        "environment",
        "provider",
        "model",
        "source",
        "user_id",
        "session_id",
        "project",
        "work_item",
        "job_run_id",
        "config_version",
        "resource_kind",
        "api_id",
        "operation",
    ] = "app"
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_range(self):
        """Reject inverted periods rather than returning misleading empty data."""
        if self.from_time and self.to_time and self.from_time >= self.to_time:
            raise ValueError("Start time must precede end time")
        return self


class Reporter:
    """All reads apply identical role, app and verified-user restrictions before aggregation."""

    def __init__(self, db):
        self.db = db

    def _args(self, principal, filters):
        require_usage_reader(principal)
        fields = tuple(
            value
            for name in _FILTER_COLUMNS
            for value in (getattr(filters, name), getattr(filters, name))
        )
        return (
            principal.tenant_id,
            *usage_scope(principal),
            filters.from_time,
            filters.from_time,
            filters.to_time,
            filters.to_time,
            *fields,
        )

    def overview(self, principal, filters=None):
        """Return independently labelled currency/provenance totals and bounded chart series."""
        filters = filters or UsageFilter()
        args = self._args(principal, filters)
        limited = (*args, self.db.settings.page_size)
        with self.db.tenant(principal.tenant_id) as connection:
            return {
                "counts": connection.execute(_SQL_COUNTS, args).fetchone(),
                "totals": connection.execute(_SQL_TOTALS, args).fetchall(),
                "breakdown": connection.execute(_SQL_BREAKDOWN, limited).fetchall(),
                "groups": connection.execute(_SQL_GROUPS[filters.group_by], limited).fetchall(),
                "trend": connection.execute(_SQL_TREND, limited).fetchall(),
                "chart_row_limit": self.db.settings.page_size,
            }

    def events(self, principal, filters=None):
        """Read a bounded page with explicit verified versus app-reported user attribution."""
        filters = filters or UsageFilter()
        args = (*self._args(principal, filters), self.db.settings.page_size, filters.offset)
        with self.db.tenant(principal.tenant_id) as connection:
            rows = connection.execute(_SQL_EVENT_PAGE, args).fetchall()
        return [self._attribution(row) for row in rows]

    def event(self, principal, event_id: UUID):
        """Return one visible attempt, including its original plan/evidence metadata."""
        args = (*self._args(principal, UsageFilter()), event_id)
        with self.db.tenant(principal.tenant_id) as connection:
            row = connection.execute(_SQL_EVENT_ONE, args).fetchone()
        if not row:
            raise HTTPException(404, "Event not found")
        return self._attribution(row)

    def _attribution(self, row):
        row["user_attribution"] = (
            "verified"
            if row["verified_user_id"]
            else "app_reported"
            if row["payload"]["user_id"]
            else "service"
        )
        return row

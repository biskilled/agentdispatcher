"""Strict metadata-only ingestion contracts; secrets and bodies have no fields here."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

class Contract(BaseModel):
    """Reject unknown fields so callers cannot accidentally persist prompt bodies."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UsageEvent(Contract):
    """One physical attempt; repeated event IDs must carry identical evidence."""

    event_id: UUID
    attempt_id: UUID
    operation_id: UUID
    occurred_at: AwareDatetime
    tenant_id: UUID | None = None
    app: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=50)
    resource_kind: Literal["llm", "api", "tool"]
    source: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    operation: str = Field(min_length=1, max_length=150)
    model: str | None = Field(default=None, max_length=100)
    api_id: str | None = Field(default=None, max_length=100)
    connection_id: str | None = Field(default=None, max_length=100)
    user_id: str | None = Field(default=None, max_length=100)
    project: str | None = Field(default=None, max_length=100)
    work_item: str | None = Field(default=None, max_length=100)
    session_id: str | None = Field(default=None, max_length=100)
    trace_id: str | None = Field(default=None, max_length=100)
    job_run_id: UUID | None = None
    config_version: str | None = Field(default=None, max_length=100)
    status: Literal["success", "error", "timeout", "cached"]
    status_code: int | None = Field(default=None, ge=100, le=599)
    duration_ms: Decimal = Field(ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    units: Decimal = Field(default=Decimal(1), ge=0, allow_inf_nan=False)


class EventBatch(Contract):
    """A bounded atomic batch from one authenticated application."""

    events: list[UsageEvent] = Field(min_length=1, max_length=1000)


class JobEvent(Contract):
    """Scheduled-run state; times are timezone-aware and tenant is credential-bound."""

    run_id: UUID
    app: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    state: Literal["running", "completed", "failed", "cancelled"]
    occurred_at: AwareDatetime
    trace_id: str | None = Field(default=None, max_length=100)


class ApiPlan(Contract):
    """Immutable effective-dated simple pricing; unsupported formulas are rejected."""

    api_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    name: str = Field(min_length=1, max_length=150)
    effective_at: AwareDatetime
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    pricing: Literal["unknown", "free", "per_unit"] = "unknown"
    unit_price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit_name: str = Field(default="request", min_length=1, max_length=50)
    charge_statuses: list[int] = Field(default_factory=lambda: [200], max_length=500)
    quota_limit: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    quota_window_seconds: int | None = Field(default=None, gt=0)
    threshold_percent: int = Field(default=80, ge=1, le=100)
    source_note: str = Field(default="User configured; not invoice verified", max_length=500)

    @model_validator(mode="after")
    def validate_plan(self):
        """Make zero cost explicit and reject partially specified quota rules."""
        if self.pricing == "per_unit" and self.unit_price is None:
            raise ValueError("per_unit pricing requires unit_price")
        if self.pricing != "per_unit" and self.unit_price is not None:
            raise ValueError("Only per_unit pricing accepts unit_price")
        if (self.quota_limit is None) != (self.quota_window_seconds is None):
            raise ValueError("Quota limit and window must be specified together")
        if any(code < 100 or code > 599 for code in self.charge_statuses):
            raise ValueError("Invalid charge status")
        return self


class Principal(Contract):
    """Validated service or user identity; never constructed from telemetry tags."""

    tenant_id: UUID
    subject_id: UUID
    role: Literal["owner", "admin", "member", "viewer", "service"]
    app: str | None = None
    environment: str | None = None
    expires_at: datetime | None = None

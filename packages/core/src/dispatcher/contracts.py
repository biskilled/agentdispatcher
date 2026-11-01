"""Strict metadata-only ingestion contracts; secrets and bodies have no fields here."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    pipeline_role: str | None = Field(default=None, max_length=100)
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
    reported_cost: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    reported_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def cost_pair(self):
        """Reported amounts require a currency; trust is derived from the credential source."""
        if (self.reported_cost is None) != (self.reported_currency is None):
            raise ValueError("reported_cost and reported_currency must be supplied together")
        return self


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
    schedule_id: str | None = Field(default=None, max_length=100)
    scheduled_for: AwareDatetime | None = None

    @model_validator(mode="after")
    def schedule_pair(self):
        """Scheduled runs identify both their registry entry and exact expected occurrence."""
        if (self.schedule_id is None) != (self.scheduled_for is None):
            raise ValueError("schedule_id and scheduled_for must be supplied together")
        return self


class Window(Contract):
    """Calendar resets use local wall time; rolling windows use elapsed time."""

    kind: Literal["rolling", "fixed", "daily", "monthly"]
    seconds: int | None = Field(default=None, gt=0)
    anchor: AwareDatetime | None = None
    timezone: str = "UTC"
    reset_hour: int = Field(default=0, ge=0, le=23)
    reset_day: int = Field(default=1, ge=1, le=28)

    @model_validator(mode="after")
    def validate_window(self):
        """Reject incomplete rules and unsupported time zones at publication."""
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown reset time zone") from error
        if self.kind in {"rolling", "fixed"} and self.seconds is None:
            raise ValueError("Elapsed windows require seconds")
        if self.kind == "fixed" and self.anchor is None:
            raise ValueError("Fixed windows require an explicit anchor")
        return self


class Tier(Contract):
    """An upper cumulative unit boundary; a null boundary covers the remaining units."""

    up_to: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    unit_price: Decimal = Field(ge=0, allow_inf_nan=False)


class QuotaRule(Contract):
    """Quota counting is independent of billing rules and never promises enforcement."""

    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    limit: Decimal = Field(gt=0, allow_inf_nan=False)
    window: Window
    statuses: list[int] = Field(default_factory=lambda: [200], max_length=500)
    timeout_units: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit_weight: Decimal = Field(default=Decimal(1), ge=0, allow_inf_nan=False)
    count_cached: bool = False
    thresholds: list[int] = Field(default_factory=lambda: [80, 100], min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_counting(self):
        """Validate outcome codes and threshold percentages before evaluating counters."""
        if any(s < 100 or s > 599 for s in self.statuses):
            raise ValueError("Invalid quota status code")
        if any(t < 1 or t > 100 for t in self.thresholds):
            raise ValueError("Quota thresholds must be between 1 and 100")
        return self


class ApiPlan(Contract):
    """Immutable declarative pricing and counting rules; no executable formulas."""

    api_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    name: str = Field(min_length=1, max_length=150)
    effective_at: AwareDatetime
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    pricing: Literal[
        "unknown", "free", "per_unit", "subscription", "graduated", "volume", "per_token"
    ] = "unknown"
    unit_price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    unit_name: str = Field(default="request", min_length=1, max_length=50)
    charge_statuses: list[int] = Field(default_factory=lambda: [200], max_length=500)
    quota_limit: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    quota_window_seconds: int | None = Field(default=None, gt=0)
    threshold_percent: int = Field(default=80, ge=1, le=100)
    source_note: str = Field(default="User configured; not invoice verified", max_length=500)
    verified_at: AwareDatetime | None = None
    pool_scope: Literal["api", "connection", "account", "endpoint"] = "api"
    billing_window: Window | None = None
    included_units: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)
    fixed_fee: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)
    tiers: list[Tier] = Field(default_factory=list, max_length=100)
    input_token_price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_token_price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    quota_rules: list[QuotaRule] = Field(default_factory=list, max_length=20)
    count_cached: bool = False

    @model_validator(mode="after")
    def validate_plan(self):
        """Make zero cost explicit and reject partially specified quota rules."""
        if self.pricing in {"per_unit", "subscription"} and self.unit_price is None:
            raise ValueError("Unit and subscription pricing require unit_price (overage rate)")
        if self.pricing not in {"per_unit", "subscription"} and self.unit_price is not None:
            raise ValueError("This pricing formula does not accept unit_price")
        if self.pricing in {"free", "unknown"} and (self.fixed_fee or self.included_units):
            raise ValueError("Free and unknown plans cannot define fees or allowances")
        if (self.quota_limit is None) != (self.quota_window_seconds is None):
            raise ValueError("Quota limit and window must be specified together")
        if any(code < 100 or code > 599 for code in self.charge_statuses):
            raise ValueError("Invalid charge status")
        if self.billing_window and self.billing_window.kind == "rolling":
            raise ValueError("Billing periods require fixed or calendar resets")
        cumulative = self.pricing in {"subscription", "graduated", "volume"}
        if (cumulative or self.included_units or self.fixed_fee) and not self.billing_window:
            raise ValueError("Cumulative pricing and allowances require a billing window")
        if self.pricing in {"graduated", "volume"}:
            bounds = [t.up_to for t in self.tiers[:-1]]
            if not self.tiers or self.tiers[-1].up_to is not None or any(b is None for b in bounds):
                raise ValueError(
                    "Tiers need increasing finite boundaries and an unlimited final tier"
                )
            if bounds != sorted(set(bounds)):
                raise ValueError("Tier boundaries must strictly increase")
        elif self.tiers:
            raise ValueError("Only graduated/volume pricing accepts tiers")
        if self.pricing == "per_token":
            if self.input_token_price is None or self.output_token_price is None:
                raise ValueError("Token pricing requires both per-token rates")
            if self.included_units:
                raise ValueError("Token allowances require a custom-unit plan")
        elif self.input_token_price is not None or self.output_token_price is not None:
            raise ValueError("Only token pricing accepts token rates")
        if self.quota_limit is not None and not self.quota_rules:
            self.quota_rules = [
                QuotaRule(
                    name="default",
                    limit=self.quota_limit,
                    window=Window(kind="rolling", seconds=self.quota_window_seconds),
                    thresholds=[self.threshold_percent, 100],
                )
            ]
        if len({q.name for q in self.quota_rules}) != len(self.quota_rules):
            raise ValueError("Quota rule names must be unique")
        return self


class ApiConnection(Contract):
    """Metadata only; provider credentials remain in the calling app's secret store."""

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    api_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    name: str = Field(min_length=1, max_length=150)
    account_pool: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    operations: list[Annotated[str, Field(min_length=1, max_length=150)]] = Field(
        default_factory=list, max_length=100
    )
    enabled: bool = True


class Principal(Contract):
    """Validated service or user identity; never constructed from telemetry tags."""

    tenant_id: UUID
    subject_id: UUID
    role: Literal["owner", "admin", "member", "viewer", "service"]
    app: str | None = None
    environment: str | None = None
    expires_at: datetime | None = None
    visible_apps: list[str] = Field(default_factory=list)
    verified_user_id: UUID | None = None
    purpose: Literal["ingest", "gateway"] = "ingest"

"""Pure decimal pricing and reset rules reused by previews, ingestion and reconciliation."""

from calendar import monthrange
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from dispatcher.contracts import ApiPlan, QuotaRule, UsageEvent, Window

ZERO = Decimal(0)


def window_bounds(rule: Window, at: datetime) -> tuple[datetime, datetime]:
    """Return half-open UTC bounds; ambiguous calendar reset times use the first occurrence."""
    at = at.astimezone(UTC)
    if rule.kind == "rolling":
        return at - timedelta(seconds=rule.seconds), at
    if rule.kind == "fixed":
        anchor = rule.anchor.astimezone(UTC)
        period = timedelta(seconds=rule.seconds)
        start = anchor + ((at - anchor) // period) * period
        return start, start + period
    local = at.astimezone(ZoneInfo(rule.timezone))
    start = local.replace(hour=rule.reset_hour, minute=0, second=0, microsecond=0, fold=0)
    if rule.kind == "daily":
        if start.astimezone(UTC) > at:
            start -= timedelta(days=1)
        end = start + timedelta(days=1)
    else:
        start = start.replace(day=rule.reset_day)
        if start.astimezone(UTC) > at:
            start = _month(start, -1)
        end = _month(start, 1)
    return start.astimezone(UTC), end.astimezone(UTC)


def _month(at: datetime, delta: int) -> datetime:
    year, month = divmod(at.year * 12 + at.month - 1 + delta, 12)
    return at.replace(year=year, month=month + 1, day=min(at.day, monthrange(year, month + 1)[1]))


def quota_units(rule: QuotaRule, event: UsageEvent) -> Decimal | None:
    """Keep unknown timeout consumption distinct from configured zero consumption."""
    if event.status == "cached" and not rule.count_cached:
        return ZERO
    if event.status == "timeout" or event.status_code is None:
        return rule.timeout_units
    return event.units * rule.unit_weight if event.status_code in rule.statuses else ZERO


def charged_units(plan: ApiPlan, event: UsageEvent) -> Decimal | None:
    """Use provider outcome rules, independently of quota counting."""
    if event.status == "cached" and not plan.count_cached:
        return ZERO
    if event.status_code is None and plan.charge_outcomes is not None:
        return event.units if event.status in plan.charge_outcomes else ZERO
    if event.status == "timeout" or event.status_code is None:
        return None
    return event.units if event.status_code in plan.charge_statuses else ZERO


def cumulative_cost(plan: ApiPlan, units: Decimal) -> Decimal:
    """Rate variable usage only; fixed subscriptions are separate, once-per-period charges."""
    units = max(ZERO, units - plan.included_units)
    if plan.pricing in {"per_unit", "subscription"}:
        return units * plan.unit_price
    if plan.pricing == "volume":
        return next(
            units * tier.unit_price
            for tier in plan.tiers
            if tier.up_to is None or units <= tier.up_to
        )
    if plan.pricing == "graduated":
        cost, lower = ZERO, ZERO
        for tier in plan.tiers:
            upper = units if tier.up_to is None else min(units, tier.up_to)
            cost += max(ZERO, upper - lower) * tier.unit_price
            if upper >= units:
                break
            lower = upper
        return cost
    raise ValueError("This formula does not price cumulative units")


def calculate_price(
    plan: ApiPlan | None, event: UsageEvent, previous_units: Decimal = ZERO
) -> tuple:
    """Compute the incremental charge; negative volume discounts remain explicit adjustments."""
    if plan is None or plan.pricing == "unknown":
        return None, None if plan is None else plan.currency, "unknown"
    if plan.pricing == "free":
        return ZERO, plan.currency, "configured_free"
    units = charged_units(plan, event)
    if units is None:
        return None, plan.currency, "unknown"
    if units == ZERO:
        return ZERO, plan.currency, "calculated"
    if plan.pricing == "per_token":
        if event.input_tokens is None or event.output_tokens is None:
            return None, plan.currency, "unknown"
        cost = (
            event.input_tokens * plan.input_token_price
            + event.output_tokens * plan.output_token_price
        )
    else:
        cost = cumulative_cost(plan, previous_units + units) - cumulative_cost(plan, previous_units)
    return cost, plan.currency, "calculated"

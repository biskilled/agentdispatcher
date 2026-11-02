"""Capability-based CLI log adapters; request totals and completion records never both bill."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5

from dispatcher.contracts import UsageEvent
from dispatcher.observations import Observation
from dispatcher.telemetry import _CONTEXT, _identifier, _scope, attributes

CLI_FIELDS = frozenset(
    {
        "event.name",
        "event.kind",
        "event.sequence",
        "event.timestamp",
        "service.version",
        "app.version",
        "session.id",
        "conversation.id",
        "model",
        "duration_ms",
        "request_id",
        "client_request_id",
        "attempt",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "cost_usd",
        "cost_usd_micros",
        "status_code",
        "input_token_count",
        "output_token_count",
        "cached_token_count",
        "cache_write_token_count",
        "env",
    }
)
_CODEX_IGNORED = {
    "codex.conversation_starts",
    "codex.startup_phase",
    "codex.user_prompt",
    "codex.tool_result",
    "codex.tool_decision",
    "codex.turn_ttft",
    "codex.websocket_request",
}
_CLAUDE_IGNORED = {
    "user_prompt",
    "assistant_response",
    "tool_result",
    "tool_decision",
    "api_refusal",
}


def number(values, field, *, integer=False):
    """Accept numeric OTLP scalars or CLI string numbers, never booleans or non-finite values."""
    raw = values.get(field)
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("Boolean usage measurement")
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise ValueError("Invalid numeric usage measurement") from None
    if not value.is_finite() or value < 0 or (integer and value != value.to_integral_value()):
        raise ValueError("Invalid usage measurement")
    return int(value) if integer else value


def claude_usage(values, name):
    """Claude input counts exclude cache tokens; supplied USD amounts are client estimates."""
    name = name.removeprefix("claude_code.")
    if name in _CLAUDE_IGNORED:
        return None
    if name not in {"api_request", "api_error"}:
        raise ValueError("Unsupported Claude event capability")
    failed = name == "api_error"
    amount = number(values, "cost_usd")
    if amount is None and (micros := number(values, "cost_usd_micros", integer=True)) is not None:
        amount = Decimal(micros) / 1_000_000
    inputs = number(values, "input_tokens", integer=True)
    cached = number(values, "cache_read_tokens", integer=True)
    written = number(values, "cache_creation_tokens", integer=True)
    return {
        "source": "claude-code",
        "provider": "anthropic",
        "status": "error" if failed else "success",
        "status_code": number(values, "status_code", integer=True) if failed else None,
        "input_tokens": None if inputs is None else inputs + (cached or 0) + (written or 0),
        "output_tokens": number(values, "output_tokens", integer=True),
        "reported_cost": amount,
        "reported_currency": "USD" if amount is not None else None,
        "duration_ms": number(values, "duration_ms"),
    }


def codex_usage(values, name):
    """Only completed streams carry billable token evidence; header-level successes are ignored."""
    if name in _CODEX_IGNORED:
        return None
    if name == "codex.api_request":
        status = number(values, "http.response.status_code", integer=True)
        if status is None:
            raise ValueError("Request outcome cannot be determined from this CLI event")
        if status is not None and status < 400:
            return None
        return {
            "source": "codex",
            "provider": values.get("dispatcher.provider", "codex-provider"),
            "status": "error",
            "status_code": status,
            "duration_ms": number(values, "duration_ms"),
        }
    if name not in {"codex.sse_event", "codex.websocket_event"}:
        raise ValueError("Unsupported Codex event capability")
    if values.get("event.kind") != "response.completed":
        return None
    inputs = number(values, "input_token_count", integer=True)
    outputs = number(values, "output_token_count", integer=True)
    if inputs is None or outputs is None:
        raise ValueError("Completion did not provide token counts")
    return {
        "source": "codex",
        "provider": values.get("dispatcher.provider", "codex-provider"),
        "status": "success",
        "input_tokens": inputs,
        "output_tokens": outputs,
        "duration_ms": None,
    }


def normalize_log(principal, resource, record):
    """Normalize known CLI capabilities and retain no bodies, user email or error messages."""
    values = {**resource, **attributes(record.get("attributes", []), CLI_FIELDS)}
    _scope(principal, values)
    name = values.get("event.name")
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("Invalid CLI event name")
    service = resource.get("service.name", "")
    if name.startswith("codex."):
        usage = codex_usage(values, name)
        session = values.get("conversation.id")
    elif name.startswith("claude_code.") or service == "claude-code":
        usage = claude_usage(values, name)
        session = values.get("session.id")
    else:
        raise ValueError("Unsupported CLI source")
    if usage is None:
        return None
    timestamp = int(record.get("timeUnixNano", 0)) or int(record.get("observedTimeUnixNano", 0))
    if timestamp <= 0:
        raise ValueError("An event or exporter observation timestamp is required for idempotence")
    identity = json.dumps(
        [
            str(principal.tenant_id),
            principal.app,
            principal.environment,
            name,
            timestamp,
            session,
            values.get("request_id"),
            values.get("client_request_id"),
            values.get("attempt"),
        ]
    )
    stable_id = uuid5(NAMESPACE_URL, identity)
    context = {field: values[key] for field, key in _CONTEXT.items() if key in values}
    # CLI cache semantics and subscription billing are not general flat token prices.
    # Report their supplied estimates or unknown, rather than silently pricing cached tokens.
    context.pop("api_id", None)
    context.setdefault("session_id", session)
    event = UsageEvent(
        event_id=values.get("dispatcher.event_id", stable_id),
        attempt_id=values.get("dispatcher.attempt_id", stable_id),
        operation_id=values.get("dispatcher.operation_id", stable_id),
        app=principal.app,
        environment=principal.environment,
        resource_kind="llm",
        operation="completion",
        occurred_at=datetime.fromtimestamp(timestamp // 1_000_000_000, UTC)
        + timedelta(microseconds=(timestamp % 1_000_000_000) // 1000),
        model=values.get("model"),
        client_version=values.get("service.version") or values.get("app.version"),
        trace_id=_identifier(record["traceId"], 32) if record.get("traceId") else None,
        **usage,
        **context,
    )
    if values.get("dispatcher.canonical_source"):
        return Observation(
            event=event,
            expected_source=values["dispatcher.canonical_source"],
            correlation_kind=values.get("dispatcher.correlation_kind", "attempt"),
        )
    return event

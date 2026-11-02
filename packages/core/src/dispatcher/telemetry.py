"""Narrow OTLP/HTTP JSON trace adapter: only metadata fields enter the usage ledger."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from dispatcher.contracts import UsageEvent
from dispatcher.ledger import Ledger
from dispatcher.observations import Observation, Observations
from dispatcher.source_health import SourceHealth

_INFERENCE = {"chat", "generate_content", "text_completion", "embeddings"}
_INTEGERS = {"gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "http.response.status_code"}
_NUMBERS = {"dispatcher.cost", "dispatcher.units"}
_ATTRIBUTES = {
    "service.name",
    "deployment.environment.name",
    "deployment.environment",
    "dispatcher.tenant_id",
    "tenant.id",
    "dispatcher.resource_kind",
    "dispatcher.billable_attempt",
    "dispatcher.provider",
    "dispatcher.operation",
    "dispatcher.source",
    "dispatcher.api_id",
    "dispatcher.connection_id",
    "dispatcher.attempt_id",
    "dispatcher.operation_id",
    "dispatcher.event_id",
    "dispatcher.canonical_source",
    "dispatcher.correlation_kind",
    "dispatcher.status",
    "dispatcher.cost",
    "dispatcher.currency",
    "dispatcher.units",
    "dispatcher.session_id",
    "dispatcher.job_run_id",
    "dispatcher.config_version",
    "dispatcher.user_id",
    "agentdesk.project",
    "agentdesk.work_item",
    "agentdesk.pipeline_role",
    "gen_ai.operation.name",
    "gen_ai.provider.name",
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "http.response.status_code",
}
_CONTEXT = {
    "project": "agentdesk.project",
    "work_item": "agentdesk.work_item",
    "pipeline_role": "agentdesk.pipeline_role",
    "session_id": "dispatcher.session_id",
    "job_run_id": "dispatcher.job_run_id",
    "config_version": "dispatcher.config_version",
    "user_id": "dispatcher.user_id",
    "api_id": "dispatcher.api_id",
    "connection_id": "dispatcher.connection_id",
}


def attributes(items, extra_scalars=frozenset()):
    """Decode permitted scalars; bodies, events and unknown attributes are dropped."""
    if not isinstance(items, list):
        raise ValueError("Attributes must be a list")
    result = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid attribute")
        name = item.get("key")
        if not isinstance(name, str) or name not in _ATTRIBUTES | extra_scalars:
            continue
        if name in result:
            raise ValueError("Duplicate usage attribute")
        value = item.get("value")
        if not isinstance(value, dict) or len(value) != 1:
            raise ValueError("Invalid usage attribute value")
        kind, scalar = next(iter(value.items()))
        if name in _INTEGERS and kind != "intValue":
            raise ValueError("Integer usage attributes require intValue")
        if name == "dispatcher.billable_attempt" and kind != "boolValue":
            raise ValueError("Billable attempt requires boolValue")
        if (
            name not in _INTEGERS | _NUMBERS | {"dispatcher.billable_attempt"} | extra_scalars
            and kind != "stringValue"
        ):
            raise ValueError("Usage labels require stringValue")
        if kind == "intValue" and type(scalar) in (int, str):
            scalar = int(scalar)
        elif kind == "doubleValue" and type(scalar) in (int, float, str):
            try:
                scalar = Decimal(str(scalar))
            except InvalidOperation:
                raise ValueError("Invalid numeric usage attribute") from None
            if not scalar.is_finite():
                raise ValueError("Non-finite usage attribute")
        elif kind == "boolValue" and type(scalar) is bool:
            pass
        elif kind == "stringValue" and isinstance(scalar, str):
            if len(scalar) > 200:
                raise ValueError("Usage label exceeds the supported length")
        else:
            raise ValueError("Usage attributes must be scalars")
        result[name] = scalar
    return result


def _identifier(value, size):
    if (
        not isinstance(value, str)
        or len(value) != size
        or any(character not in "0123456789abcdefABCDEF" for character in value)
        or int(value, 16) == 0
    ):
        raise ValueError("Invalid trace/span ID")
    return value.lower()


def _scope(principal, values):
    for name in ("tenant.id", "dispatcher.tenant_id"):
        if name in values and str(values[name]) != str(principal.tenant_id):
            raise HTTPException(403, "Telemetry tenant is outside the SDK credential scope")
    for name, expected in (
        ("service.name", principal.app),
        ("deployment.environment.name", principal.environment),
        ("deployment.environment", principal.environment),
        ("env", principal.environment),
    ):
        if name in values and values[name] != expected:
            raise HTTPException(403, "Telemetry application/environment is outside the SDK scope")


def normalize(principal, resource, span):
    """Normalize physical usage; aggregate agent/workflow spans are not billable attempts."""
    values = {**resource, **attributes(span.get("attributes", []))}
    _scope(principal, resource)
    _scope(principal, values)
    operation = values.get("gen_ai.operation.name")
    if operation in _INFERENCE:
        kind = "llm"
    elif values.get("dispatcher.billable_attempt") is True:
        operation, kind = values.get("dispatcher.operation"), values.get("dispatcher.resource_kind")
    else:
        raise ValueError("Unsupported non-usage span")
    trace_id, span_id = _identifier(span.get("traceId"), 32), _identifier(span.get("spanId"), 16)
    stable_id = uuid5(
        NAMESPACE_URL,
        f"dispatcher:{principal.tenant_id}:{principal.app}:{principal.environment}:{trace_id}:{span_id}",
    )
    start, end = int(span["startTimeUnixNano"]), int(span["endTimeUnixNano"])
    if start <= 0 or end < start:
        raise ValueError("Invalid span interval")
    occurred = datetime.fromtimestamp(start // 1_000_000_000, UTC) + timedelta(
        microseconds=(start % 1_000_000_000) // 1000
    )
    status = values.get("dispatcher.status", "success")
    span_status = span.get("status", {}).get("code", 0)
    if type(span_status) is not int or span_status not in {0, 1, 2}:
        raise ValueError("Unsupported OTLP status code")
    http_status = values.get("http.response.status_code")
    if span_status == 2 or (http_status is not None and int(http_status) >= 400):
        status = "timeout" if status == "timeout" else "error"
    event = UsageEvent(
        event_id=values.get("dispatcher.event_id", stable_id),
        attempt_id=values.get("dispatcher.attempt_id", stable_id),
        operation_id=values.get("dispatcher.operation_id", stable_id),
        occurred_at=occurred,
        app=principal.app,
        environment=principal.environment,
        resource_kind=kind,
        source="otel",
        trace_id=trace_id,
        operation=operation,
        provider=values.get("dispatcher.provider")
        or values.get("gen_ai.provider.name")
        or values.get("gen_ai.system"),
        model=values.get("gen_ai.response.model") or values.get("gen_ai.request.model"),
        requested_model=values.get("gen_ai.request.model"),
        status=status,
        status_code=http_status,
        duration_ms=Decimal(end - start) / 1_000_000,
        input_tokens=values.get("gen_ai.usage.input_tokens"),
        output_tokens=values.get("gen_ai.usage.output_tokens"),
        units=values.get("dispatcher.units", 1),
        reported_cost=values.get("dispatcher.cost"),
        reported_currency=values.get("dispatcher.currency"),
        **{field: values[key] for field, key in _CONTEXT.items() if key in values},
    )
    if values.get("dispatcher.canonical_source"):
        return Observation(
            event=event,
            expected_source=values["dispatcher.canonical_source"],
            correlation_kind=values.get("dispatcher.correlation_kind", "attempt"),
        )
    return event


class Telemetry:
    """Use existing authentication, ledger pricing and reference correlation for OTLP traces."""

    def __init__(self, db):
        self.db, self.ledger, self.observations = db, Ledger(db), Observations(db)

    def export(self, principal, body):
        """Return OTLP partial-success counts without persisting rejected or unsupported content."""
        return self.export_signal(principal, body, "traces", normalize)

    def export_signal(self, principal, body, signal, normalizer, extra_scalars=frozenset()):
        """Share envelope validation, pricing, idempotence and diagnostics across OTLP signals."""
        prepared, rejected, count = [], 0, 0
        resource_key, scope_key, record_key, rejected_key = (
            ("resourceSpans", "scopeSpans", "spans", "rejectedSpans")
            if signal == "traces"
            else ("resourceLogs", "scopeLogs", "logRecords", "rejectedLogRecords")
        )
        try:
            for resource in body[resource_key]:
                resource_attributes = attributes(
                    resource.get("resource", {}).get("attributes", []), extra_scalars
                )
                _scope(principal, resource_attributes)
                for scope in resource.get(scope_key, []):
                    for span in scope.get(record_key, []):
                        count += 1
                        if count > self.db.settings.request_limit:
                            raise HTTPException(413, "Too many spans in one export")
                        try:
                            item = normalizer(principal, resource_attributes, span)
                            if item is not None:
                                prepared.append(item)
                        except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
                            rejected += 1
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(400, "Invalid OTLP envelope") from None
        accepted = 0
        for item in prepared:
            try:
                if isinstance(item, Observation):
                    self.observations.ingest(principal, [item])
                else:
                    self.ledger.ingest(principal, [item])
                accepted += 1
            except HTTPException as error:
                if error.status_code not in {409, 422}:
                    raise
                rejected += 1
        message = "unsupported_invalid_or_conflicting_usage" if rejected else None
        SourceHealth(self.db).record(principal, "otlp-" + signal, accepted, rejected, message)
        return (
            {"partialSuccess": {rejected_key: str(rejected), "errorMessage": message}}
            if rejected
            else {}
        )


def routes(db, service):
    """Accept only bounded, uncompressed OTLP JSON with a current tenant/app SDK credential."""
    router = APIRouter(prefix="/api/otlp")
    adapter = Telemetry(db)

    async def read_body(request, resource_key):
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise HTTPException(415, "Use OTLP/HTTP JSON encoding")
        if request.headers.get("content-encoding", "identity") != "identity":
            raise HTTPException(415, "Use uncompressed OTLP JSON")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > db.settings.telemetry_max_bytes:
                raise HTTPException(413, "OTLP request exceeds the configured byte limit")
        try:
            body = json.loads(content)
        except (ValueError, RecursionError):
            raise HTTPException(400, "Invalid OTLP JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get(resource_key), list):
            raise HTTPException(400, "OTLP resources must be an array")
        return body

    @router.post("/v1/traces")
    async def traces(request: Request, principal=Depends(service)):
        """Drop all non-allowlisted content before pricing or storage."""
        body = await read_body(request, "resourceSpans")
        return await run_in_threadpool(adapter.export, principal, body)

    @router.post("/v1/logs")
    async def logs(request: Request, principal=Depends(service)):
        """Accept supported CLI usage records; ignore prompts and other non-usage logs."""
        from dispatcher.cli_telemetry import CLI_FIELDS, normalize_log

        body = await read_body(request, "resourceLogs")
        return await run_in_threadpool(
            adapter.export_signal, principal, body, "logs", normalize_log, CLI_FIELDS
        )

    return router

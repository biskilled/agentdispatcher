# Authenticated OpenTelemetry ingestion

Dispatcher accepts **OTLP/HTTP JSON traces** at `/api/otlp/v1/traces`. Send the
application's dedicated SDK key as `Authorization: Bearer …`. Tenant, application
and environment come from that credential. Google/browser sessions and LiteLLM
virtual keys cannot ingest telemetry. Keys are rechecked for expiry/revocation on
every export. Use HTTPS outside an intentionally private local network.

The adapter follows [OTLP JSON encoding and partial-success responses](https://opentelemetry.io/docs/specs/otlp/).
The direct endpoint accepts uncompressed JSON only. It does not accept protobuf,
gRPC, metrics or logs yet. A standard collector can translate its supported incoming
transport into JSON for this endpoint. Unsupported usage spans return a partial-success
rejection count, also visible under **Connections → Telemetry delivery**. An accepted
HTTP export is not proof that every span was priced or that every application is covered.

## Scope and supported metadata

Set `service.name` to the SDK key's application and `deployment.environment.name`
to its environment. Either may be omitted and defaults to the authenticated scope;
a conflicting value is rejected. `dispatcher.tenant_id` and `tenant.id`, when supplied,
must match the credential. Resource attributes provide defaults; span attributes
provide per-request work-item context. These labels never grant access.

| Attribute | Meaning |
| --- | --- |
| `gen_ai.operation.name` | Supported physical inference: `chat`, `generate_content`, `text_completion`, `embeddings` |
| `gen_ai.provider.name` / legacy `gen_ai.system` | Provider label |
| `gen_ai.request.model`, `gen_ai.response.model` | Requested and served models |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | Reported integer token counts; missing counts stay unknown |
| `dispatcher.billable_attempt=true` | Explicitly marks a custom API/tool physical attempt |
| `dispatcher.resource_kind`, `dispatcher.operation`, `dispatcher.provider` | Required custom-attempt kind (`api`/`tool`), safe operation template and provider label |
| `dispatcher.api_id`, `dispatcher.connection_id`, `dispatcher.units` | Catalog pricing and quota attribution |
| `dispatcher.cost`, `dispatcher.currency` | Optional exact amount/currency pair, labelled app estimate rather than invoice verified |
| `agentdesk.project`, `agentdesk.work_item`, `agentdesk.pipeline_role` | Stable resource defaults or changing span context |
| `dispatcher.session_id`, `dispatcher.job_run_id`, `dispatcher.config_version`, `dispatcher.user_id` | Session/run/version and app-reported user metadata |
| `dispatcher.event_id`, `dispatcher.attempt_id`, `dispatcher.operation_id` | Optional UUID correlation identities |
| `dispatcher.canonical_source`, `dispatcher.correlation_kind` | Reference an already instrumented source by `attempt` or `operation`; do not add a second charge |

Without explicit IDs, stable tenant/app/trace/span-derived IDs make exported-span
retries idempotent. Physical provider retries must have distinct span/attempt IDs.
A parent agent/workflow span is not inferred to be another provider request. Tool
invocation counts do not reveal hidden upstream LLM use: instrument owned nested
calls separately and declare any tool charge explicitly. Missing prices stay unknown.

Only the allowlisted scalar metadata enters PostgreSQL. Span names, prompt/response
messages, exceptions, events, URLs, request bodies and unknown attributes are discarded.
Configure instrumentation not to collect content in the first place, particularly
when using other exporters. Avoid secrets in the explicitly allowed labels. The
[GenAI semantic convention source](https://github.com/open-telemetry/semantic-conventions-genai)
is evolving; unsupported fields are not silently treated as zero usage.

## Optional collector profile

The pinned collector uses the official
[OTLP HTTP exporter](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.164.0/exporter/otlphttpexporter/README.md)
and [bearer receiver authenticator](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.164.0/extension/bearertokenauthextension/README.md).
It has no debug exporter. Its backend URL stays inside the Compose network.

1. Create an SDK key for the intended tenant/app/environment in the browser.
2. Set `DISPATCHER_OTLP_SDK_KEY` to that key and `DISPATCHER_COLLECTOR_TOKEN` to a
   separate random receiver secret in the private deployment environment.
3. Run `docker compose --profile telemetry up -d collector`.
4. Point that application's exporter to the collector and send its receiver token
   in the Authorization header. Set the resource labels to the key's app/environment.

One collector instance is bound to **one app/environment credential**, not a shared
cross-tenant master key. Use separately configured instances for separate credentials,
or send authenticated JSON directly to the API. The profile exposes no host ports;
publish only the intended listener or use a private network. `OTEL_HTTP_HOST` and
`OTEL_HTTP_PORT` configure its listener. The collector buffers asynchronously: its
transport acknowledgement does not bypass the API's live SDK-key checks. Revoking
the upstream SDK key prevents subsequent persistence even if the collector buffers
an export; rotate the receiver secret independently when changing collector access.

`DISPATCHER_TELEMETRY_MAX_BYTES` bounds direct API request bytes (default 1 MiB).
`DISPATCHER_REQUEST_LIMIT` bounds spans per export; the collector sends batches of
at most 100. `DISPATCHER_SOURCE_STALE_SECONDS` controls the "No recent exports"
indicator. That indicator may also mean an idle app; it is not proof of an outage.
Delivery counters include replays and are separate from unique billable attempts.

CI's `scripts/collector_smoke.py` runs the real pinned image with synthetic credentials,
a tool plus two nested inference spans, exact totals, duplicate exports, discarded
content, tenant spoofing and revoked-key rejection. No paid provider is called.

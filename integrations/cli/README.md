# CLI monitoring

Use one billing authority per CLI: LiteLLM for traffic routed through the gateway,
or telemetry for direct/subscription traffic. Do not count both independently.
Dispatcher does not copy browser cookies, scrape quota pages or discover local apps.
The dashboard works on macOS, Windows and mobile; CLI export runs on the CLI's host.

## Codex

The adapter is verified against installed Codex **0.164.0** using a loopback synthetic
Responses provider (`scripts/verify_codex_telemetry.py`). It accepts completed SSE or
WebSocket response events with token counts; successful HTTP headers and intermediate
stream messages do not add attempts. HTTP failures with a status are separate attempts.
Missing completion counts and ambiguous failures are rejected with coverage diagnostics.
Completion latency and invoice cost are unknown, not zero. The CLI can use custom
providers, so the default provider label is `codex-provider`; an explicitly configured
`dispatcher.provider` resource attribute can supply a known provider.

Configure an OTLP HTTP JSON log exporter in the user's Codex config. Set its endpoint
to your Dispatcher `/api/otlp/v1/logs`, and its Authorization header to a dedicated
SDK key through your deployment's secret/configuration facility. Keep prompt logging
off. Scope the key to the emitted `service.name` and environment: the verified
`codex exec` fixture emits `codex_exec`; interactive or other clients may emit a
different service name. The resource `env` must match the key's environment.
Use the installed client's supported exporter-header configuration; do not commit
the credential. [Official configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
and [telemetry guidance](https://learn.chatgpt.com/docs/config-file/config-advanced).

The source version is displayed in Connections. Formats are validated by their
capabilities rather than accepting every future version by number. Other versions
need a fixture check before relying on complete coverage. Metrics, session totals
and quota snapshots are not physical-attempt charges.

## Claude Code

Enable telemetry and OTLP logs; send them to the authenticated collector using its
HTTP/protobuf receiver. Disable metrics and traces for this ingestion path to avoid
overlapping signals. The collector converts logs to JSON and uses a separate app-scoped
SDK key for `/api/otlp/v1/logs`. Give the key the emitted service name (`claude-code`)
and configured environment. Keep prompt, tool-detail and raw-body export disabled.
Set configuration in the user's launcher or managed settings, not the repository.
[Official Claude Code monitoring documentation](https://code.claude.com/docs/en/monitoring-usage).

The adapter accepts `api_request` and `api_error` records with OTLP timestamps,
model, duration and available token/cost evidence. USD values are **client estimates**,
including integer-millionth values; they are never labelled invoices or actual
subscription charges. Input totals include reported cache read/write tokens. Without
cost evidence, cost stays unknown. Synthetic official-format fixtures pass; a real
Claude provider run has not been performed or billed by this verification.

## Delivery, privacy and scope

Use a separate collector per app/environment credential, or direct authenticated
JSON for a capable client. The supplied Compose collector has a private receiver;
expose it only through your authenticated TLS deployment boundary. It now accepts
traces and logs; metrics are not a usage ledger source. Do not send unrelated tenants
through one collector key.

The adapter drops bodies, prompts, outputs, email, host paths and error text. It
retains only normalized usage and attribution. The event timestamp (or supplied exporter
observation timestamp when the event timestamp is zero), scoped source
and request/session identity form a stable replay key. Conflicting replays are
rejected. Unknown usage shapes appear in rejected-export counters, and stale exports
appear in Connections. A source that has never connected cannot be discovered.
These telemetry-only clients have no model-routing controls. LiteLLM policies apply
only to calls actually routed through registered gateway keys.

For overlapping sources that can propagate the same attempt/operation identifiers,
`dispatcher.canonical_source` plus the correlation attributes creates a non-billing
observation. Standard CLI logs do not guarantee those identifiers match gateway
callbacks. Choose one source in that case; no heuristic deduplication is claimed.

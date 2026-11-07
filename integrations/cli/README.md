# CLI monitoring

Use one billing authority per CLI: LiteLLM for traffic routed through the gateway,
or telemetry for direct/subscription traffic. Do not count both independently.
Dispatcher does not copy browser cookies, scrape quota pages or discover local apps.
The dashboard works on macOS, Windows and mobile; CLI export runs on the CLI's host.

## CodexBar account sync

The **AgentDispatcher Collector** includes the [CodexBar](https://github.com/steipete/CodexBar)
account reader and Python runtime in one download. It is an additional reader, not
an alternative to Codex, Cursor or Claude Code. No separate CodexBar or SDK install
is required. It does not intercept prompts or change coding tools.

In **Sources → CLI account usage**, create a connection for a device/user, download
the collector, unzip it and open a terminal in its folder:

```sh
./AgentDispatcherCollector --configure
./AgentDispatcherCollector --interval 300
```

Enter the Dispatcher app root (without `/llm/v1`) and the account sync key when
prompted. Configuration is stored in an owner-only file; `--config` or
`DISPATCHER_COLLECTOR_CONFIG` selects another location. `DISPATCHER_URL` and
`DISPATCHER_ACCOUNT_KEY` override saved values. Omit `--interval` for one check;
Ctrl-C stops polling. This does not install a startup service.

Use `--provider copilot` to select a reader, or `--provider codex --all-accounts`
for all configured accounts for one provider. Otherwise enabled provider settings
apply. Provider sign-in may be required on the local device. Use `--reader --help`
to inspect the bundled reader's options. Existing JSON exports can be uploaded
using `--file usage.json`. HTTP redirects never forward the sync credential.

The current bundle supports macOS Apple Silicon and Intel (runtime-tested on Apple
Silicon). It is ad-hoc signed, not Apple notarized. See the bundled README and
checksum before granting macOS approval. Native Windows collection and packaged
Linux collection are not included; the dashboard works from any browser.
[Packaging and licensing details](../../packaging/collector/README.md).

Source/SDK users can still run `python -m agentdispatcher_sdk.codexbar` with their
own installed reader (`CODEXBAR_BIN` override). This developer path is not needed
for the downloadable collector. LiteLLM gateway traffic needs no local collector;
account limits are optional and distinct from per-request usage.

Raw files stay local. The bridge selects only provider/account display labels, source,
version, measured timestamps, quota windows, reset times, credit balances, provider
period spend and generic detail rows. Raw errors, cookies, access tokens, paths,
prompts and provider dashboards are not forwarded. Account labels may include email;
these are reported labels, not verified Dispatcher identity. Access uses tenant/app
permissions or explicit verified-user delegation, never an email-label match.

Provider IDs are dynamic; support follows the installed CodexBar fetchers and their
available measurements. This does not promise every desktop feature: local cost-history
scanning, charts, notifications and native widgets are not included. A provider's
period spending is not a per-request invoice. Unknown readings remain unknown;
failed fetches are unavailable; old or undated measurements are stale. Configure
`DISPATCHER_ACCOUNT_STALE_SECONDS` on the API (default 900) for freshness display.

Snapshots replace the latest account state in PostgreSQL with tenant RLS; replaying
or polling cannot add charges. Their dates do not filter historical requests. Model,
trace and job filters suppress account cards because aggregate account balances have
no such attribution. Provider/app/source/user filters apply to both where applicable.
The existing attribution-retention policy removes old snapshots; complete tenant
erasure includes them. Enterprise rollout installs/configures the local sync on each
participating device or authorized collection host; one UI connection does not
silently enroll every CLI in an organization.

## Direct CLI request telemetry (advanced)

These adapters are separate from account balances. Use them only for request traffic
that does not already report through LiteLLM. Create their reporting keys in
**Sources → Application LLM calls → Advanced reporting**.

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

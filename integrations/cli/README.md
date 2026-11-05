# CLI monitoring

Use one billing authority per CLI: LiteLLM for traffic routed through the gateway,
or telemetry for direct/subscription traffic. Do not count both independently.
Dispatcher does not copy browser cookies, scrape quota pages or discover local apps.
The dashboard works on macOS, Windows and mobile; CLI export runs on the CLI's host.

## CodexBar account sync

For subscription/account usage, reuse [CodexBar](https://github.com/steipete/CodexBar)
and its [CLI](https://github.com/steipete/CodexBar/blob/main/docs/cli.md). Install it
on the machine holding the authorized provider sessions; configure and authenticate
its enabled providers. The Dispatcher browser cannot read another machine's sessions.
This optional integration currently uses upstream macOS/Linux builds. Native Windows
collection is not supplied; Windows/mobile browsers can view already synced accounts.

In **Sources → CLI account usage**, create a connection for a device or user. Then,
from a clone of this repository, install the separately packaged SDK (Python 3.12+):

```sh
pip install ./packages/sdk
export DISPATCHER_URL="https://your-dispatcher-host"
export DISPATCHER_ACCOUNT_KEY="<CLI account sync key shown once>"
python -m agentdispatcher_sdk.codexbar --interval 300
```

`DISPATCHER_URL` is the public app root, without `/llm/v1`. Optionally set
`CODEXBAR_BIN` to the installed executable. Omit `--interval` to sync once from a
scheduler. `--provider copilot` selects one upstream provider; otherwise CodexBar's
enabled-provider configuration is used. `--provider codex --all-accounts` syncs all
configured accounts for that provider. To inspect/export before uploading:

```sh
codexbar usage --format json > usage.json
python -m agentdispatcher_sdk.codexbar --file usage.json
```

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

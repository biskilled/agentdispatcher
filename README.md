# AgentDispatcher

Operators can use the optional [PostgreSQL backup/recovery profile](documents/output/recovery.md)
to restore into a new database with fresh credentials. The monitoring dashboard also
exports the selected authorized usage as JSON, preserving exact decimal costs and
rejecting oversized selections instead of silently truncating them.
Tenant administrators can also configure [attribution retention](documents/output/retention.md);
complete workspace deletion is a separate, explicit offline operator action.

React monitoring for application API calls, LLM requests and scheduled work, backed by a tenant-isolated PostgreSQL ledger. One repository contains independently runnable API, worker, UI and Python SDK packages.

**Development preview:** monitoring, administration, SDK integrations and configuration controls are implemented and tested. Production release is blocked by live authentication acceptance and upstream container advisories. See [implementation status](documents/output/implementation-progress.md) and [release evidence](documents/output/release-verification.md) for the exact remaining work.

## Try the synthetic demo

Requires Python 3.12+ to generate configuration and Docker with Compose v2. Images/dependencies need downloading on first build; the running demo makes no external provider calls and requires no paid account.

```sh
python3 scripts/configure.py
docker compose up --build -d
docker compose --profile demo run --rm demo
```

Open the short-lived `sign_in` link printed by the demo command and click **Continue to workspace**. The workspace contains 18 synthetic attempts across three applications, including deliberately unknown LLM prices. Rates are fixtures, not actual vendor prices. The demo creates its own tenant and does not change existing tenant data. Repeating the command reuses the seeded workspace and issues a new login link, subject to throttling.

The UI binds to `127.0.0.1:8088` by default. Change `UI_PORT` and `DISPATCHER_PUBLIC_URL` together in `.env`. PostgreSQL, API, gateway and collector have no published management ports. Data survives service/container restarts in the `database` volume. Do not remove that volume if you need the data.

**Verification note:** local PostgreSQL/API/SDK/browser tests passed, including backup/restore and tenant isolation. [GitHub CI](https://github.com/biskilled/agentdispatcher/actions/runs/41378379070) passed clean Compose startup, the synthetic demo, independent service restarts, persistence, collector trace/log intake and real LiteLLM tenant/key/accounting checks. Docker is unavailable locally; container verification runs in CI. The separate security workflow remains a release gate; functional success does not clear security findings.

## Create a real workspace

Configure SMTP in `.env`, then provision the initial owner from the operator CLI:

```sh
docker compose exec api dispatcher create-tenant --name "My workspace" --email "owner@example.com"
```

The email address alone is not proof of identity. The owner signs in using a single-use email link before receiving dashboard access. Use **Access** to invite members, assign roles/app views, and revoke invitations. The invited person signs in independently, then pastes the invitation token into **Join another workspace**. Concurrent membership changes cannot remove the last owner. Tenant creation remains operator-controlled.

For Google sign-in, configure `DISPATCHER_GOOGLE_CLIENT_ID` and `DISPATCHER_GOOGLE_CLIENT_SECRET`. Register the exact `${DISPATCHER_PUBLIC_URL}/api/auth/google/callback` redirect URI in Google. Accounts use the OIDC issuer and subject; matching email addresses are **not** automatically linked. **Link a Google account** requires a recent sign-in (`DISPATCHER_REAUTH_SECONDS`) and an unchanged browser session throughout linking. OAuth state is single-use in PostgreSQL. A newly created Google account has no workspace access until membership is provisioned.

For remote/mobile access, put the UI behind HTTPS, set `DISPATCHER_PUBLIC_URL` to that origin, enable `DISPATCHER_SECURE_COOKIES=true`, and configure the listen address/reverse proxy intentionally. The React application runs in desktop and mobile browsers; no desktop app is needed.

## Instrument an application

Install only the small SDK into your application's environment:

```sh
pip install ./packages/sdk
```

Create a tenant key in **SDK keys**, scoped to the application's name and environment. Store it in the application's environment or secret store; never in browser code, prompts or YAML committed to Git.

```python
import os
from agentdispatcher_sdk import Monitor

monitor = Monitor(
    endpoint=os.environ["DISPATCHER_ENDPOINT"],
    key=os.environ["DISPATCHER_SDK_KEY"],
    app=os.environ["APPLICATION_NAME"],
    environment=os.environ["APPLICATION_ENVIRONMENT"],
)

with monitor.job("scheduled-analysis"):
    with monitor.operation(provider="market-data", operation="price", api_id="market-data") as usage:
        response = existing_http_client.get(configured_provider_url)
        usage["status_code"] = response.status_code
        response.raise_for_status()

# At application shutdown, not after each request:
flushed = monitor.close()
```

Wrap each physical request attempt, including each retry/page. Reuse `operation_id` for a shared logical operation. Use `monitor.record(resource_kind="llm", ...)` for measured provider token counts. Use `heartbeat()` for long-running jobs. The SDK carries current OpenTelemetry trace IDs when available and separates concurrent job contexts. Use `monitor.context(project=..., work_item=..., config_version=...)` for attribution, and explicitly pass `monitor.export_context()` through queue messages into the receiving worker's context. Exported context excludes credentials.

Export runs in a bounded background queue. Delivery retries retain event IDs; business requests are never retried by the monitoring SDK. `delivered`, `failed`, `dropped` and the result of `close()` expose loss. Abrupt process termination can lose queued telemetry. Optional `MonitoredTransport` and `AsyncMonitoredTransport` from `agentdispatcher_sdk.http` wrap HTTPX transports without inspecting bodies/URLs; supply an operation template and provider/API/connection IDs. They measure time to response headers, not streaming body duration. Additional language SDKs remain pending.

### Avoid overlapping charges

For a LiteLLM call, use `with monitor.gateway() as context:` and send `context` as
the request's `metadata.dispatcher_context`. Local manual/HTTP/provider hooks inside
that block become non-billable observations. LiteLLM's deployment callbacks own the
physical attempts, including retries/fallbacks, and carry the same logical operation
ID. Keep the block around the complete client operation. The SDK key and LiteLLM key
must belong to the same tenant/app/environment. Context contains no credentials.

When combining the HTTPX transport and `ProviderObserver` directly, choose one
billable source. Set `canonical_source="provider-observer"` on the transport when
the provider observer will supply final token usage. Pass the original response or
exception to the observer so it can reuse the attached physical-attempt identifiers.
Without this setting the HTTP transport owns the attempt, and the provider observer
adds a reference. Do not discard the correlation extension by converting the response
to a plain dictionary before observing it. A missing provider callback stays visible
as missing evidence; it is not substituted with an invented zero cost.

Other adapters may send `POST /api/observations` with an `observations` list containing
`event` (the usage contract), `expected_source`, and `correlation_kind` (`attempt` or
`operation`). These records never consume quotas or add charges. **Connections** shows
which references have matching billable evidence. Matching is scoped to tenant,
app/environment and the exact attempt or operation ID. References may arrive before
or after the upstream record; original prices remain immutable. Uncorrelated events
with unrelated IDs cannot safely be guessed into one charge. Instrumenting one app
does not discover other uninstrumented applications.

## Accounting and security boundaries

- Runtime PostgreSQL roles cannot bypass RLS. Tenant context is transaction-local and comes from authenticated credentials. A separate narrowly granted auth connection owns identity, membership and credential lookups; no public route exposes those tables directly.
- Human access and service ingestion are separate. SDK keys cannot read reports or administer tenants. Key verifiers are SHA-256 hashes of high-entropy random secrets; secrets are shown once. Expiry/revocation and membership changes are checked on each request.
- Owner/admin can see tenant-wide usage. Members see their own verified usage and explicit app grants; viewers see granted apps only. An empty viewer grant grants no usage access. A service may attach a short-lived token issued by `POST /api/auth/delegate` through `monitor.user(token)`. The token is bound to the user's current session, tenant and app; logout/removal invalidates it. SDK-reported user IDs never confer read permission.
- Identical event replays are idempotent; altered evidence with the same event/attempt ID is rejected. Use the correlation modes above when multiple observers see one request; submit billable physical attempts from one selected source.
- Pricing supports explicit unknown/free, per-unit, per-token, subscription/overage, graduated and volume tiers. Historic events retain their plan and original cost. Fixed fees appear separately once per observed pool/billing period; unobserved subscription periods are not inferred. Cumulative marginal charges allocate in ingestion order within the event-time billing period, so late-arriving calls can consume the remaining allowance. Volume discounts can produce negative marginal charges. A revised plan does not silently re-rate history. Monetary values are PostgreSQL decimals and JSON strings.
- Account/connection/API/operation pools support independent quota status rules, unit weights, unknown timeout consumption, rolling/fixed/daily/monthly windows, time zones and deduplicated worker alerts. Calendar resets use the first occurrence of ambiguous wall time; monthly reset days are 1–28. Remaining amounts are local estimates with explicit unknown counters, not provider guarantees or hard enforcement. **Budgets** accepts provider statements for comparison and signed refunds/corrections linked to original events. Importing a statement never adds its amount to the ledger; external refresh integrations remain pending.
- No request/response body fields exist in the ingestion contract. Unknown fields are rejected. Applications must still avoid putting secrets in allowed labels. OIDC access logging is disabled in the provided server/proxy configuration.

## Services and optional integrations

| Component | Entrypoint | State |
| --- | --- | --- |
| API | `uvicorn dispatcher.api:create_app --factory` | Auth, catalog, intake and monitoring reads |
| Worker | `dispatcher-worker` | Tenant-scoped run health, expected schedules, leases, budget/quota alerts |
| UI | `npm run dev` / static Vite build | Desktop/mobile monitoring and administration |
| Migrations | `python scripts/migrate.py` | Sole schema owner, separate deployment credentials |
| LiteLLM | Compose `gateway` profile | Managed virtual keys, model restrictions, per-attempt callbacks |
| MCP tools | Compose `mcp` profile or standalone stdio | Session-bound usage/session/experiment reads and consented policy writes |
| OTel collector | Compose `telemetry` profile | Authenticated app-scoped traces, JSON ledger export and rejection diagnostics |

`docker compose --profile gateway up --build -d gateway` builds and starts LiteLLM after you supply `LLM_PROVIDER_MODEL` and `LLM_API_KEY`. It is internal-only; connect applications on an authorised service network. Its master key is operator-only. Use **LLM keys** to provision an application/environment key with explicit model aliases. The gateway verifies revocation and scope before each call and exports metadata-only usage using a separate internal callback secret. These calculated prices are not invoices. End-to-end tests use synthetic provider responses inside the real LiteLLM image and verify SDK/gateway correlation without duplicate charges. Paid provider invoices have not been validated. OpenRouter can be configured as a LiteLLM upstream.

The collector forwards authenticated traces to `/api/otlp/v1/traces` and supported
CLI logs to `/api/otlp/v1/logs`. It is bound to
one tenant/app/environment SDK key and has no debug exporter. The API validates live
credentials, normalizes supported usage spans, discards body content and reports
rejected usage under **Connections**. See the [telemetry connection guide](integrations/telemetry/README.md)
for supported fields, correlation, private receiver credentials and coverage limits.
See [CLI onboarding](integrations/cli/README.md) for Codex/Claude capabilities and
coverage limits. Generic metrics ingestion is outside the implemented trace/log contract.

The optional [MCP tools service](services/mcp/README.md) has its own dependency lock
and container. Create a dedicated credential in **Tool access**; SDK keys cannot read
monitoring data. MCP grants preserve the user's current permissions and end on logout
or revocation. This is the monitoring-tool interface; instrumentation of arbitrary
third-party MCP calls is a separate adapter.

Tenant-bound AgentData database credentials, a Cube model and sample questions are in
[the AgentData integration](integrations/agentdata/README.md). The database credential
enforces tenant isolation even when generated SQL changes or omits a tenant filter.

The [AgentDesk integration](integrations/agentdesk/README.md) provides explicit tenant
binding, personal account linking, live identity checks, authorized session/usage reads
and effective-time work-item/pipeline-role attribution. It requires the included
AgentDesk identity endpoint to be deployed; matching email addresses never grant access.

## Model policies and experiments

Use **Model policies** to allow model aliases, select a primary route and ordered
fallbacks, and declare required capabilities. Every selected alias must also be
allowed by the application's LiteLLM virtual key. Policies apply to an app/environment;
new gateway requests read the current revision. Provider URLs and secrets remain in
the operator's LiteLLM configuration. Capability lists are operator declarations,
not automatic proof that a provider implements a feature correctly.

**Experiments** creates immutable weighted variants, a seed and quality/latency/sample
gates. The browser starts with two equally weighted variants; the API accepts up to
ten configurable weights. Attach the experiment to a compatible policy. Use the same
job-run UUID (or logical operation UUID for a single-call task) in every gateway request's
`metadata.dispatcher_context`. Assignment is deterministic for the entire task.

An app can call `monitor.route(model_alias, task_id)` to obtain the assignment before
starting a multi-step job. This explicit routing lookup is synchronous and fails when
the policy service is unavailable; ordinary telemetry exports remain asynchronous.
Copy `experiment_id`, `assignment_id` and `variant` into `monitor.context(...)` for
other task/evaluation calls, setting `usage_category="evaluation"` for evaluator spend.
The same identifiers on gateway calls come from trusted server selection, not caller
tags. The ledger separately records requested alias, served model and policy revision.

At task completion, call `monitor.task_outcome(assignment_id, status=..., quality=...,
duration_ms=..., coverage_complete=..., fees_accounted=..., currency=..., evaluator=...)`.
Quality is an app-provided score from 0 to 1. Declare coverage complete only after
recording all task attempts and evaluator calls. `additional_cost` includes allocated
fees or other task charges not already present in the ledger; do not count them twice.
Final feedback is immutable, and export retries remain idempotent.

Results include spend from failed/retried attempts and failed tasks, evaluator spend
and declared allocations, divided by successful tasks. Missing feedback, unknown costs,
mixed currencies, incomplete coverage, insufficient samples or failing quality/latency
gates prevent promotion. App-attested observations are never labelled proven future
savings. An eligible candidate can be promoted explicitly: this stores the evaluation
snapshot and activates a new routing revision. **Routing history** restores any prior
revision, including an earlier experiment configuration. YAML changes still follow
their separate review/reload workflow.

## Review application YAML

An installation operator grants access through `DISPATCHER_CONFIG_SOURCES`, a JSON
map of named sources. Existing `.env` files need `DISPATCHER_CONFIG_SOURCES={}` when
upgrading. Each entry specifies `tenant_id`, `app`, `environment`, `kind` (`file`,
`api`, or `git`), `writable`, and permitted `fields`. File/Git sources also specify
an authorised `root` and relative `path`; API sources specify `endpoint` and optional
`token_env` naming a secret environment variable. Git sources require `author_name`
and `author_email`. Mount authorised directories into both API and worker containers
explicitly. For Git sources, set `INSTALL_GIT=true` and rebuild the core image. API
tokens, SSH keys and known-host configuration must be supplied separately to the
containers that need them; the source map contains only secret environment names.

A field such as `llm.model` uses `{"kind":"model","models":["approved-model-a",
"approved-model-b"]}`. Numeric fields specify `kind: number` or `integer` plus
`minimum`/`maximum`; boolean fields use `kind: boolean`. Operators must verify model
capability compatibility before allowing a candidate. A cheaper price alone does
not establish quality equivalence. No arbitrary string/secret/prompt edits are allowed.

In **Configuration**, scan a source, edit permitted values, prepare a review, then
apply the displayed scalar diff. Comments and unrelated content stay unchanged.
Aliases, duplicate keys, flow-mapping edit paths, multiline scalar edits, escaping
paths and symlink file targets fail explicitly. PostgreSQL stores safe parameter
values, source revisions, hashes and review history, never original YAML or prompts.

API sources must implement atomic strong-ETag `If-Match` writes. Local files use
atomic replacement with hash checks; external writers must coordinate because
ordinary filesystems offer no atomic compare-and-swap against uncooperative writers.
Git creates an unpushed, deterministic review branch while preserving the checkout/index.
An optional `publish_remote` names an operator-configured Git remote. With that grant,
**Publish review branch** pushes only the prepared branch, without force or a deployment
branch refspec. PR creation, merging and deployment remain explicit external actions.
Retrying a Git write after a crash reuses the branch after verifying its contents.

Saving is separate from activation. After reloading the actual YAML bytes, the app
calls `monitor.configuration_activation(change_id, sha256_of_loaded_bytes, success)`
and attributes requests with `monitor.context(config_version=sha256_of_loaded_bytes)`.
File/API changes can restore previous parameter values after failed activation,
provided no external edit followed the applied version. Rollback also requires an
application reload; it does not imply deployment. For Git, rollback creates a second
review branch against the currently deployed/merged revision. Publish and merge it,
then report activation using the rollback digest and the same change ID.

The worker polls sources every `DISPATCHER_CONFIG_POLL_SECONDS` (default 60). Each app
instance should periodically call `monitor.configuration_runtime(source_id, instance_id,
sha256_of_loaded_bytes, success=True)`. **Loaded configuration** distinguishes matching,
drifted, failed, stale and missing evidence. Reports expire after
`DISPATCHER_CONFIG_RUNTIME_TTL` seconds (default 300); a source unavailable to the worker
cannot confirm parity. Only reporting instances are covered. Instance IDs must be stable
within an app/environment; they are metadata, not authorization. Older queued reports
cannot replace newer observations. Source or permission changes invalidate old evidence.

**Check evaluated alternatives** uses the existing experiment engine. Configure the
experiment's `configuration_source` and exact `configuration_digest`, and include that
digest as `config_version` on its usage records. Suggestions require a matching app,
environment, source revision and allowed model, plus successful-task cost, quality,
latency and coverage gates. Prices alone never produce suggestions. **Prepare evaluated
review** rechecks the evidence and stores its snapshot with the diff. Approval and
activation remain separate; configured gates are not statistical proof of savings.

`scripts/verify_configuration_ui.py --env-file <local-env>` exercises real connected
YAML editing, failed activation and rollback on desktop/mobile against an isolated
fixture API and the configured disposable PostgreSQL database. Build the UI first.

## Development and verification

Use Python 3.12+ and Node 24. Install the runtime lock, then the project and development tools. On this organisation's workstations, `.venv` and `node_modules` must be symlinks into `/Users/user/Documents/venv` and `/Users/user/Documents/node_modules`; install npm dependencies at the shared destination with `npm ci --prefix ...` so npm does not replace the symlink.

```sh
python -m pip install -r requirements.lock
python -m pip install -e '.[dev]'
npm ci
ruff check packages scripts tests
pytest -q
npm run build
python scripts/notices.py
```

Integration tests require `TEST_DATABASE_URL` pointing to a **disposable PostgreSQL owner database**. They create application roles/schema and synthetic tenants. Without it, PostgreSQL tests skip; skipped tests are not proof of isolation. CI supplies one. SDK tests run without a database.

For local browser tests, run API/UI against the same database with a private environment file containing the `DISPATCHER_*` settings, `DISPATCHER_DEMO_ENDPOINT`, `UI_PORT` and `BACKEND_URL`. Then:

```sh
python scripts/verify_local.py --env-file /path/to/private-local.env
```

This seeds synthetic data through the real SDK, checks desktop/mobile screens with Playwright, and revokes its temporary browser session. It never puts the session secret in command-line arguments. Install Playwright Chromium if not already available.

## Built on

Thanks to the maintainers of FastAPI, Starlette, Pydantic, Psycopg/PostgreSQL, Authlib, HTTPX, OpenTelemetry, React, Vite, Lucide, LiteLLM and the other dependencies that make this project possible. AgentDispatcher is Apache-2.0; dependencies retain their own terms, including Psycopg's LGPL terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), the generated [runtime notices](third_party/notices.json), and **Open-source licenses** in the UI. No QuotaBar or CodexBar code has been copied into this implementation.

# AgentDispatcher — current product specification

Use case: **US10000**
Revision: **2026-11-01**
Status: **Approved; implementation in progress.** See [verified implementation coverage](implementation-progress.md).

This revision incorporates the user's monitoring, embedded-agent, tenant storage, deployment and open-source requirements. It supersedes conflicting details in the 2026-10-19 design export, especially desktop-first delivery and the unvalidated 2–3 week estimate. The original export remains intact in AgentDesk.

## Product purpose

AgentDispatcher is an Apache-2.0 open-source, self-installable app in the AgentDesk ecosystem. A responsive React/TypeScript monitoring UI works on desktop and mobile; lightweight reusable SDKs/connectors inside apps capture LLM requests, scheduled jobs, workers and MCP calls. LiteLLM is the request gateway, OpenTelemetry carries execution context, and PostgreSQL is the authoritative tenant-isolated store for all durable product data.

Monitoring attributes usage by tenant, user or service identity, app, environment, project/work item, job/run/step, session, MCP server/tool, provider/model, source and prompt/config version. Join SDK telemetry to gateway/provider billing records without double counting. Show actual/reported charges, calculated costs, subscription fees and estimated API-equivalent value separately; unknown cost or incomplete coverage is never presented as zero. Include retries/fallbacks, job outcomes, heartbeats, missed/stuck runs, budgets, alerts and reconciliation. Track CLI and later web usage to the extent supported by each source; telemetry-only sources are visible but not controlled by gateway routing.

The configuration section connects to authorised app YAML through a repository, app API or local connector; inventories prompts/model settings, tracks versions and runtime adoption, proposes compatible lower-cost alternatives using workload evaluations, and supports reviewed diffs, controlled writes and rollback. YAML remains the app configuration source; tenant-scoped snapshots and change history live in PostgreSQL. Prompt content capture is off by default; evaluations use explicitly permitted samples or synthetic fixtures.

Ship independently deployable UI, Dispatcher API, background worker, LiteLLM gateway and OTel collector from one monorepo, with shared domain/contracts and one migration owner. Keep the default install minimal: Docker Compose, PostgreSQL, documented environment configuration and an offline demo with no provider key. No mandatory Kubernetes, Redis, broker or commercial service. AgentTrade's shared LLM client plus one scheduled job is the first end-to-end integration. OpenRouter is an optional upstream through LiteLLM, not a required dependency.

Reuse single-purpose classes/methods/modules; favour composition, short functions, explicit errors, clear public docstrings and comments explaining why. Configuration and SQL follow org standards. Credit every shipped open-source component through LICENSE, THIRD_PARTY_NOTICES, README Built on, an in-app licenses view and dependency/license checks. Preserve AgentDesk work-item/role attribution, tenant-scoped AgentData access, model policies, experiments, caching and optional later browser coverage. Current detailed specification: documents/output/agentdispatcher-specification.md. This revision supersedes the desktop-first design and the earlier unvalidated 2–3 week delivery estimate.

General API monitoring extension (2026-11-01): Monitor free and paid non-LLM APIs through the same reusable SDK and tenant-isolated PostgreSQL ledger, including market-data requests in scheduled jobs and user-query flows. LiteLLM remains the main LLM gateway; general API calls can go directly to their provider with SDK instrumentation and do not require a new universal proxy or desktop application. React admin provides a tenant-owned API catalog: stable API ID, connection/account reference, environment, operation/endpoint patterns, plan, independent rate limits/allowances, billing units, prices/currency, included units, subscription fee, overage/tier rules, effective dates, reset policy and alert thresholds. Store source/verification date and distinguish configured, observed and provider-reported limits. Credentials remain in the app or encrypted secret store.

The SDK identifies an API/connection by stable ID and propagates tenant, user/service, app, feature, job/run and trace context. Provide supported HTTP-client hooks plus manual record/custom-unit interfaces. Record physical attempts, logical operations, status, latency, timeouts, retry/pagination/batch/cache semantics and response-reported units without capturing sensitive bodies or raw URL query values. Count requests, quota units and billed units separately. Rules are declarative and versioned; backend pricing is authoritative. Unsupported protocols/units require explicit instrumentation or an adapter, not automatic discovery claims.

Free usage still has volume, quota and reliability metrics; zero cost requires an explicitly free plan. Unknown rates/limits stay unknown. Threshold alerts are observational by default and cannot guarantee provider-wide quota availability when calls bypass instrumentation. Shared account/key pools, concurrent apps, late/replayed events and plan changes must not double count or silently rewrite history. Rate windows, billing periods, resets and status-dependent charging are independently configurable. User-entered/provider-imported pricing is not automatically a verified invoice. Fixed subscription expense is counted once; per-call allocation is a separately labelled analytic view.

Authentication clarification (2026-11-01): Human access supports Google sign-in and verified email sign-in; passwordless email links are the initial design assumption. Resolve users, tenant memberships and roles server-side, including AgentDesk identity integration. SDKs use dedicated tenant-scoped service API keys, preferably separate per app/environment, with only a cryptographic verifier/hash stored in PostgreSQL. The SDK transmits the original random secret over TLS; a stored hash is never a client credential. Keys identify services, not human users. Tenant and permissions come from validated credentials, never telemetry tags.

## General API monitoring and admin catalog

Added 2026-11-01. AgentDispatcher monitors arbitrary instrumented API operations as well as LLM requests. The primary user experience remains the React browser dashboard on desktop/mobile; no desktop installation is needed for backend schedulers or user-query flows.

### Collection paths and boundaries

- LLM calls continue through **LiteLLM**, the main LLM gateway, with SDK context.
- Non-LLM APIs may be called directly by the app and observed through the same SDK. No universal HTTP proxy is required.
- Support reusable hooks for supported HTTP clients plus explicit operation wrappers/manual usage recording for vendor libraries and custom units. HTTP REST is the initial automatic scope; other protocols/streaming need explicit measurements or adapters.
- Users register a provider/API and connection in React admin and bind the SDK to its stable ID. New request/unit-priced APIs need configuration and a binding, not a provider-specific code release.
- Automatic instrumentation only sees calls through supported hooks. Out-of-process calls or hidden retries require instrumentation and are declared as coverage gaps.
- Monitoring itself never retries the business request, consumes a paid API to test connection, or changes application responses/exceptions. Export is bounded and independent of business execution.
- SDK observations and gateway/provider records correlate to one attempt rather than duplicating spend. Use one shared event contract, pricing implementation and quota evaluator.
- Browser-generated telemetry is untrusted client reporting; authoritative billing attribution should come from authenticated server-side SDK/provider evidence.

### React/admin configuration

| Setting | Purpose |
| --- | --- |
| API ID, display name, category | Reference LLM, market-data or other services consistently |
| Tenant connection/account alias and environment | Associate calls with a plan and credential pool without recording the key |
| Operation names and route templates | Attribute endpoints without collecting raw query strings or private path IDs |
| Quota scope | Key/account, connection, endpoint or declared shared pool; distinguish from per-user analytic allocations |
| Rate windows and billing cycles | Requests/credits per rolling or fixed window; cycle start, reset time zone and grace rules |
| Independent count rules | Specify which outcomes and units consume each rate/allowance counter |
| Unit and price | Requests, credits, records, bytes, duration or explicitly supplied units; decimal amount and currency |
| Plan model | Explicit free, per-unit, fixed subscription, included allowance, graduated/volume tiers and overage |
| Thresholds | Configurable usage percentages, remaining units, currency budgets and error/latency alerts |
| Evidence and version | Source link/admin entry, last verification time, effective dates and audit history |

Provide declarative validated rules, a synthetic pricing preview and permission-controlled publishing. No arbitrary scripts or automatic remote URL probing. Users may supply current contracted terms, or optional adapters may import provider-reported account limits. Display configured, observed and provider-reported values separately with timestamps; do not claim automatic discovery of current commercial terms.

CoinGecko and Yahoo Finance are example catalog entries. No undocumented endpoint is promised as a supported official API, and no unverified Yahoo quota or perpetual free tier is assumed. Explicitly free plans display zero charge; unknown pricing remains unknown. User-entered operational thresholds can be tracked even when provider limits are unpublished.

### SDK measurements

Record resource kind (LLM/API/tool), API/connection/operation IDs, tenant, user or service identity, app/environment, feature, job/run/step and trace context. Include logical operation ID and physical attempt ID, timing, HTTP outcome/exception category, measured units, declared cache state, retry/pagination/batch information and provider request ID where available.

Count attempts separately from logical calls. Pagination makes multiple upstream requests; a batch can be one request with many billable units. Cache hits that do not reach a provider are distinguishable from actual calls. Failure, 429 and timeout do not imply a universal zero or nonzero charge; each counter uses its configured charging rule, with uncertainty when the provider outcome is unknown. Capture only allowlisted quota headers/fields and aggregate units; redact credentials, cookies, URL queries and private identifiers. Request/response bodies remain off by default.

Instrumentation cannot infer unseen transport retries. Explicitly prevent overlap when both automatic and manual instrumentation observe the same attempt. Billing-relevant events are not sampled away. Missing/stale events must be visible rather than silently presenting complete totals.

### Pricing, quotas and PostgreSQL

Extend the existing tenant-isolated PostgreSQL ledger with API catalogs, connections, quota pools, effective-dated plans/rate rules, snapshots, counters and subscription charges. Global provider templates may be shared read-only; tenant connections, contracts and usage remain private. Preserve source measurements separately from derived costs and use event-time plan versions. Retroactive re-rating is explicit and audited.

Request count, quota consumption, billed units and monetary expense are independent metrics. Count subscription fees once per account/cycle; label optional per-user/job allocations separately and never add them again to actual spend. Preserve refunds/adjustments as evidence-backed entries. Distinguish graduated tiers from volume pricing. Unsupported formulas remain unsupported rather than producing invented charges.

Aggregate configured shared account/key limits across observed apps in the permitted pool. Another tenant's usage must not be exposed; cross-tenant account sharing needs an explicit authorised model. Local observations cannot prove global remaining quota when uninstrumented consumers use the same account. Show provider snapshots alongside observed usage and reconciliation drift.

Monitoring and alerting are the default. Distributed hard quota enforcement would require atomic shared reservations, consistent failure/timeout policy and no bypassing clients; it is separate scope. Do not market passive SDK counters as guaranteed provider limit enforcement.

### First demonstration and acceptance

An AgentTrade scheduled fixture fetches market data through the generic API SDK, calls an LLM through LiteLLM and shows both beneath one run. Also demonstrate a user-query flow using the same integration. Use synthetic, clearly labelled plan values in demos; live vendor terms must be configured/verified separately.

- A tenant admin registers a previously unknown API, connection and free/paid plan through React, and a wrapped or manually recorded call appears under its API ID without adding provider-specific Dispatcher code.
- A scheduled AgentTrade fixture includes one non-LLM API operation and one LLM request in the same trace; the dashboard shows distinct and combined costs without double counting.
- Two independent quota rules can count all attempts for a rate window while counting only configured successful statuses for billing credits; retries, pagination, batches, cache hits, 429s and ambiguous timeouts follow documented rules.
- Deterministic fixtures verify free, per-request, custom-unit, subscription-with-included-units, tiered/overage and unknown pricing; historical events retain the effective plan version and fixed fees are counted once.
- Per-connection quota windows, budgets, threshold alerts, stale/missing coverage and observed-vs-provider remaining values are visible. Distributed hard enforcement is outside passive monitoring and must not be claimed.
- Cross-tenant API catalogs, telemetry, pricing, exports and plan edits are access-controlled; sensitive bodies, credentials and raw query strings are absent from default telemetry.

### New tasks

- **TA10001 — Admin API catalog and versioned provider plans**: Create tenant-scoped catalog/connection and plan CRUD endpoints with React admin forms. Users register stable IDs for custom APIs, operation/endpoint templates, quota scope/account-key pools, rate/billing windows, reset policy, unit definitions, status-dependent counting, free allowances, subscription fees, per-unit/tiered/overage pricing, currency and thresholds. Persist effective-dated revisions, source/last-verified date, audit and role permissions in PostgreSQL. Validate rules declaratively; no arbitrary scripts, automatic endpoint probes or plaintext keys. Preview synthetic usage charges before publishing. SDK binds calls to IDs; config-only changes cover generic request/unit pricing. Unknown provider terms or counters remain unknown. CoinGecko/Yahoo Finance are example connection names, not guarantees of fixed free tiers or official supported APIs. Dependencies: TA10011, TA10010. Acceptance: a new custom API can be created and metered without code changes; version changes preserve history; pricing preview and cross-tenant/admin-only tests pass.
- **TA10002 — Shared API quota and pricing engine with mixed-workload fixtures**: Extend shared accounting behind LLM/API adapters to distinguish logical operations, physical attempts, quota consumption and charged units. Implement decimal pricing for explicit free, request/custom-unit, fixed subscription with included units, graduated versus volume tiers and overage plans; unsupported formulas fail explicitly. Quota rules independently specify counted outcomes, unit weights, connection/account/endpoint pool and rolling/fixed/billing windows with reset time zone. Handle refunds/adjustments as evidence-backed entries; aggregate invoices and allocated fixed fees must not double count. Deduplicate retries versus exports, apply effective plan at event time, expose price/coverage uncertainty and provider-reported snapshots separately. Emit threshold alerts with deduplication; monitoring does not guarantee hard quota enforcement across processes. Reuse PostgreSQL worker and SDK, no new service. Dependencies: TA10011, TA10012, TA10000 and API catalog. Acceptance: deterministic fixtures exercise success/error/429/timeout, retry/pagination/batch/cache, overlapping worker runs, late arrivals, plan changes and two tenants. AgentTrade demo combines a custom market-data call and LiteLLM analysis, with per-provider and total run cost matching unique billable events. Synthetic fixture limits/prices are explicitly labelled and do not assert current vendor terms.

### Source checked for the design

CoinGecko distinguishes successful-request monthly credit consumption from all-attempt minute rate limiting. This motivates independent count rules rather than one universal request counter. Its published limits vary by plan and source, so values must be verified against the connected account rather than hardcoded. [CoinGecko credit accounting](https://support.coingecko.com/articles/1864417806-how-does-coingecko-api-count-the-api-usage-credit).

## Product surfaces

- **Monitoring:** responsive React UI for desktop/mobile; overview, jobs/runs, sessions/traces, connections/coverage, budgets and licenses. Integrates with AgentDesk and can be installed independently.
- **Configuration and optimisation:** connect authorised application YAML, discover prompts and settings, correlate real use, evaluate alternatives and apply reversible configuration changes.
- **Embedded integration:** small SDK/connector in consuming apps. Instrument shared LLM clients and job entrypoints once; monitoring itself requires no LLM.

## Service and repository boundaries

| Independently deployable component | Responsibility |
| --- | --- |
| React/TypeScript/Vite UI | Tenant-authorised monitoring and configuration views; calls the API and holds no provider secrets |
| Dispatcher API (Python/FastAPI) | Identity/permissions, tenant-scoped queries and ingestion, gateway integration, connector/control endpoints and Dispatcher MCP read/control tools |
| Background worker | PostgreSQL-backed durable tasks/leases; schedule health, alerts, reconciliation, retention, YAML polling and evaluation orchestration |
| LiteLLM gateway | Provider calls, virtual keys, model policies/routing and supported MCP gateway operations |
| OpenTelemetry Collector | Receive/forward instrumented app/CLI telemetry to Dispatcher intake |
| PostgreSQL | Authoritative durable application data, with separate ownership/access for gateway persistence |

One Git monorepo contains all services and focused shared packages. Each service has its own process/container, configuration, health/readiness checks and restart lifecycle; separate directories alone do not satisfy this requirement. Communicate through versioned contracts; avoid imports into another service's internals. Share attribution, event validation, pricing and connector interfaces once. One migration owner applies application schema changes. API and worker are separately deployed consumers of shared application code.

Docker Compose is the default install; no mandatory Kubernetes, Redis, extra message broker, observability SaaS or commercial gateway feature. PostgreSQL task leasing is sufficient for the initial worker. The worker monitors AgentTrade's own scheduler rather than replacing its business scheduling. A local app connector is optional when remote access is insufficient; SDKs are libraries installed in the app, not a compulsory additional central service.

## Authentication, tenant membership and SDK credentials

Status: approved target design; initial implementation and verification coverage are tracked in [implementation progress](implementation-progress.md). Google sign-in and email sign-in are required; passwordless email links are the initial assumption for email (password login is not implied).

### Human sign-in and access

Use one shared authentication/authorisation boundary with adapters for AgentDesk and standalone Google/email login. Validate Google ID tokens server-side (signature, issuer, audience and expiry), bind the login response to the originating flow (state/nonce and PKCE where applicable), and identify accounts by issuer plus subject. Require verified email for email-dependent onboarding. Google's stable subject must be used instead of treating an email address as a permanent identifier. [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

Email login verifies mailbox control using single-use expiring links, with only token verifiers stored. Configure delivery, public URL, callback allowlist, token lifetime and throttling centrally; use generic responses to limit account enumeration. Do not consume login tokens on email-scanner prefetch; require a deliberate completion step. Keep tokens out of logs and referrers. Linking Google/email/AgentDesk identities requires an authenticated account-linking flow, never an automatic merge on matching email. [OWASP account linking](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#secure-federated-account-linking).

Use secure HttpOnly session cookies with suitable SameSite/CSRF protection, session rotation, configurable expiry and server-side logout/revocation. Persist durable identity/session state in PostgreSQL. Reuse maintained authentication libraries and the same permission checks across API, MCP, UI-facing operations and workers.

A user can belong to multiple tenants. Login proves identity; tenant membership and role determine access. Tenant selection is checked on each request. Existing-tenant access requires an accepted invitation or validated authorised AgentDesk membership sync; a verified email/domain alone grants no membership. Initial tenant/owner creation is explicit and controlled. Revocation or membership removal must affect subsequent authorisation without trusting stale browser state.

| Role/principal | Default access |
| --- | --- |
| Owner | Tenant administration and ownership/membership lifecycle |
| Admin | Tenant usage, API plans, configuration and SDK key management |
| Member | Own usage and explicitly assigned app/project views; no tenant administration |
| Viewer | Read-only access to explicitly granted views; no mutations |
| SDK service | Ingestion for its assigned tenant/app/environment; no human/admin access |

Centralise the permission matrix; sensitive reports/exports, configuration writes and API catalog edits require the same checks as UI actions. Tenant-wide analytics is an explicit grant. Protect the last-owner invariant and audit role/key changes.

### Dedicated tenant SDK keys

Issue a cryptographically random opaque secret, shown once to an authorised tenant admin. Each key belongs to exactly one tenant and service principal; allow multiple keys per tenant so apps/environments can rotate independently. Prefer a separate key per app/environment instead of a single shared tenant master key.

The SDK sends the original secret over TLS in an authentication header. PostgreSQL stores only a cryptographic verifier/hash plus a public lookup ID, tenant/principal, scopes, app/environment restrictions, creation/expiry/revocation/last-used metadata. Never derive a key from a tenant ID, email or password, and never accept the stored verifier as a bearer credential. Use reviewed secret-generation/verifier primitives with constant-time comparison.

Admin controls issue, rotate (with explicit bounded overlap), revoke and inspect metadata. Revocation must invalidate any auth cache and deny subsequent requests. Application secret storage holds the original key; React/browser/mobile bundles and logs must never contain it. Browser clients submit through their authenticated app backend. Keep Dispatcher ingestion keys, LiteLLM virtual keys and provider credentials distinct.

Derive tenant/service/app scope from validated credentials. Reject conflicting tenant/app/environment values in events and batch items. An SDK key does not prove a human user: store the authenticated service principal separately from an app-reported actor ID, namespaced to tenant/app and labelled as reported. Verified user attribution requires a validated delegated identity and membership mapping; neither reported nor verified attribution grants extra privileges. Schedulers normally run as services with optional initiating-user attribution.

Authenticate every SDK/OTel ingress route; keep internal collector/gateway endpoints private or equivalently authenticated so clients cannot bypass tenant checks. Workers carry server-established tenant context. Unknown/revoked credentials fail visibly without exposing secrets; exporter failures follow bounded buffering/drop reporting and do not silently change identity.

### Required verification before claiming auth works

- Google and email sign-in work on desktop/mobile; invalid issuer/audience/signature, expired tokens, mismatched state/nonce and replayed email links are rejected. Email sign-in and delivery configuration are documented.
- Verified login alone grants no existing tenant membership. Invite acceptance, tenant selection, owner/admin/member/viewer permissions and removal are tested with two tenants and multiple users. Matching email/domain cannot silently merge accounts or grant membership.
- Tenant SDK key issuance shows the secret once; storage and logs contain no recoverable key. Tenant/app/environment scopes, expiry, rotation and revocation are enforced on every ingestion path.
- An SDK key cannot access human/admin routes or claim another tenant/app. User attribution is labelled verified or app-reported; unverified actor metadata cannot grant access or impersonate a user.
- Logout, revoked sessions, removed memberships and revoked SDK keys cease authorising subsequent requests; asynchronous workers and PostgreSQL pooled connections preserve the verified tenant boundary.

Add account-linking takeover attempts, invite expiry/replay, role escalation, forged batch ownership, direct collector bypass and concurrent pooled-connection tests. Verify no plaintext keys/email-link tokens enter PostgreSQL, ordinary telemetry, exports or logs. Use real configured Google/email delivery for a documented live smoke test in addition to deterministic automated tests. Authentication is part of the first monitoring slice, not deferred until after usage ingestion.

Work ownership remains TA10003 (identity/authorisation), TA10011 (persistence/isolation), TA10010 (UI) and TA10012 (SDK); no duplicate use case or separate identity service is required.

## PostgreSQL and tenant isolation

All durable product data belongs in PostgreSQL: tenant/app/user/service mappings, connection health, schedule/job/run/step state, sessions/traces/tool calls, usage attempts, pricing versions, subscriptions, policies, budgets, config snapshots/diffs, experiments/evaluation results, reconciliation evidence, audit events and retention metadata.

The minimal default is **one PostgreSQL cluster with tenant-isolated rows in the application schema**. "Per tenant" means enforced data ownership and access, not a mandatory database/container per tenant. Dedicated tenant databases are a future deployment option if required.

- Tenant-owned tables have mandatory tenant identity; tenant-aware foreign keys, uniqueness and indexes prevent cross-tenant joins/references.
- Authorise tenant membership from validated credentials, including AgentDesk identities and app service credentials. Never trust caller-supplied telemetry tags as authentication.
- Enforce API/worker scoping and PostgreSQL row-level security. Runtime roles cannot bypass isolation; use separate migration/admin roles. Set and reset tenant context safely on pooled connections.
- Bind AgentData read-only credentials/roles to their permitted tenant; arbitrary query filters are not sufficient access control.
- Keep LiteLLM-owned tables and credentials separate from the application's migrations. Cross-store ingestion is a controlled adapter boundary.
- Store monetary values as decimal amounts with currency; preserve original rates and pricing provenance.
- Keep credentials in env/encrypted secret storage; never in Git, plaintext YAML snapshots, prompt logs or ordinary event metadata.
- App YAML remains the configuration source of truth; PostgreSQL contains authorised redacted snapshots/version history. Files in the repo are source/distribution artifacts, not a competing runtime database.
- Bounded transient SDK buffers/spools are transport only. Declare their loss/overflow policy; final durable product state is PostgreSQL.
- Backups, restore, retention, export and deletion preserve tenant scope. Cross-tenant tests must include background tasks, aggregate queries, connectors and pooled connections.

## AgentTrade: first integration and verification example

1. Instrument AgentTrade's shared LLM client once and wrap one scheduler job entrypoint.
2. Register its job definition, schedule/time zone and configurable expected-run grace period.
3. On every execution, create a job run and trace with app/environment/tenant, executing service, optional beneficiary user and trigger.
4. Attach run/step/attempt IDs and effective prompt/config version to LLM requests; propagate context through asynchronous tasks, queues, workers, HTTP and owned MCP services.
5. Correlate provider/gateway usage with SDK events; record requested and served model/provider, tokens including caching, latency, outcome and priced attempts.
6. Emit completion/failure/cancellation and heartbeats as appropriate. Missing start, lost heartbeat, process crash and exporter outage must produce distinct observable states.
7. Display app -> job definition -> run -> step/tool -> individual request attempts on desktop and mobile.
8. Compare the run total to distinct priced requests. Re-delivering an event or receiving both SDK and gateway records must not increase its cost.

An initial integration should not require changing every call site when a shared client already exists. Calls bypassing the client/gateway need a supported adapter; automatic coverage must never be claimed for uninstrumented execution. App metadata is validated against credential scope.

Telemetry must not block AgentTrade business jobs. Use bounded export, backoff, deduplication, configurable flush and explicit loss/staleness indicators. Accounting events must not be randomly sampled away; optional detailed traces can use a separately declared sampling policy. A background process must flush on orderly shutdown, with coverage gaps visible after abrupt termination.

## Monitoring and accounting contracts

Dimensions include tenant, user/service, team, app, environment, project/work item, agent role, job/run/step, session, trace, MCP server/tool, provider/model, client/source, experiment variant and prompt/config version. Persist source event ID, logical request ID and individual attempt ID where available, with timestamps and provenance.

An MCP call is not inherently an LLM charge. Instrument owned tool internals or ingest explicit supplier usage to reveal nested costs. A job/tool displays a rollup over distinct child charges, plus separately evidenced tool fees; do not charge for parent rollups a second time. Keep real billed retries/fallbacks distinct from duplicate event delivery. Capture the actual serving provider when an intermediary routes a request.

Show these separately:

| Cost category | Treatment |
| --- | --- |
| Provider-reported or reconciled charge | Preserve source evidence and reconciliation status |
| Calculated API cost | Token/billable-unit usage multiplied by the applicable versioned rates |
| Subscription fee | Actual plan expense for the period |
| Estimated API-equivalent value | Comparison metric, not additional billed expense |
| Unknown/missing | Explicitly unknown or incomplete, never silently zero |

Do not add aggregate provider invoices to the same request charges. Reconciliation compares evidence and reports drift. Include caching, charged retries/fallbacks, applicable fees and evaluation spend. Any currency conversion must retain the original amount and rate/time provenance.

Register schedules to detect missed runs; observing only successful calls cannot establish that an expected job never started. Handle time zones, overlapping runs, configurable grace/timeout policies, late completion and provisional states. Show source last-seen time and coverage alongside spend. Cost alerts use configurable thresholds. Hard budget enforcement has documented concurrency and gateway-failure semantics; it cannot enforce traffic outside the gateway.

## MCP, CLI and ecosystem connections

- LiteLLM is the default LLM/MCP gateway foundation; OpenRouter is an optional upstream for model/provider selection.
- Expose authorised remote MCP servers, preserve upstream credential boundaries and trace owned nested LLM work.
- A central deployment cannot reach a user's local stdio MCP server without an authorised connector running in the appropriate environment.
- Claude Code/Codex integrations are capability/version-aware: gateway mode where supported, telemetry otherwise. Subscription and web coverage may be incomplete or estimated.
- Runtime policies control only gateway-routed traffic. The UI must distinguish observable from controllable connections.
- AgentDesk provides identity/membership and work-item/session/role context; validate it server-side. Mid-session changes use per-request context and effective-time mappings.
- Dispatcher exposes tenant-authorised usage/session/experiment MCP reads and permission-controlled policy writes.
- AgentData receives a tenant-scoped read-only PostgreSQL connector and semantic model for usage queries. Its own LLM calls carry tenant/feature/version context.
- Optional web-chat estimation and desktop packaging follow the core monitoring release.

## YAML configuration and optimisation workflow

Connect through explicitly authorised Git/repository access, app configuration API or local connector. Reuse one connector interface with source-specific adapters. Inventory prompts, model aliases, parameters, fallback chains and source revisions. Preserve existing YAML as authoritative and associate runtime calls with its effective version.

Read access permits discovery, not writes. Within granted permissions, offer a schema-validated exact diff, reject stale source revisions, preserve unrelated settings/comments where supported, apply atomically and record actor/source/before/after/reason. For Git-backed configuration use a reviewable branch/PR when configured. Unsupported YAML constructs fail explicitly instead of being destructively normalised.

A file write is not deployment: detect or trigger an authorised reload/redeploy, verify the running app's effective configuration version and report pending/failed activation. Support rollback to a known version and validate activation again.

Recommend alternatives using workload evidence, compatible context/tool/structured-output requirements, representative evaluations and declared quality thresholds. Compare total cost per successful task, latency, reliability and applicable fees; include evaluation cost. With metadata-only capture, use synthetic fixtures or explicitly permitted/redacted samples. Do not label a cheaper model equivalent without quality evidence. Keep candidate recommendations distinct from proven savings and actual realised savings.

## Engineering and release rules

### reusable minimal code

Write once, reuse many: keep AgentDispatcher minimal with single-purpose classes, short well-named methods/functions and shared modules as the single source of each behaviour. Prefer composition and clear data flow; no duplicated pricing, attribution, validation or connector logic, speculative abstractions or silent failures. Add short public docstrings explaining purpose and non-obvious constraints; comments explain why. Match surrounding style, remove dead code, validate boundaries, configure URLs/ports/paths/limits through env/config and keep secrets out of source. SQL is named _SQL_* constants at file top with parameterised queries; migrations are appended and idempotent. Use focused tests for meaningful behaviour.

### postgresql tenant data

PostgreSQL is the authoritative store for all durable AgentDispatcher product data: tenant/app identities, usage/price records, jobs/runs/traces, policies, configuration snapshots, evaluations and audit/history. Every tenant-owned record, query, join, worker and export must preserve authenticated tenant scope; enforce RLS with non-bypass runtime roles and tenant-aware constraints. Minimal default is one PostgreSQL cluster with tenant-isolated shared application schema, not one database per tenant; physical per-tenant databases are an optional later deployment choice. Separate LiteLLM-owned storage/roles. App YAML remains its source; version snapshots/history live in PostgreSQL. Secrets stay in encrypted secret storage/env; SDK spools are bounded transient transport buffers. Test at least two tenants and pooled connections. Telemetry tags are attribution, never authentication.

### independent services single monorepo

Use one Git monorepo with real independently deployable services: responsive React/TypeScript UI, Python/FastAPI Dispatcher API, dedicated background worker/scheduler, LiteLLM gateway and OTel collector, backed by PostgreSQL. Each service has its own entrypoint/container, configuration, health check and restart lifecycle. Share focused packages/contracts; no copied domain logic or imports into another service's internals. One migration owner controls application schema. Default Compose install uses PostgreSQL-backed background coordination and needs no Kubernetes, Redis or external broker. Monitor external app schedulers without taking over their business scheduling.

### open source easy install and credits

AgentDispatcher is intended for public Apache-2.0 open-source distribution. Keep dependencies and custom code minimal; reuse suitable open-source components while preserving attribution and license obligations. Supply a clean-checkout Docker Compose quickstart, documented env example, offline deterministic demo requiring no provider key, separate live-provider smoke instructions and concise testing/contributing docs. Maintain LICENSE, THIRD_PARTY_NOTICES.md, required upstream license texts, README Built on, in-app licenses and dependency/license checks for shipped components/assets/images. No LiteLLM enterprise code or mandatory prohibited AGPL/commercial dependencies; OpenRouter is optional. Pin reviewed supported releases and verify advisories at implementation/release rather than relying on old minimum-version claims.

### react monitoring and embedded sdk

React is primarily the responsive desktop/mobile monitoring interface, not the app-execution agent. Use a small reusable OpenTelemetry-based integration inside consuming apps at their shared LLM client and scheduler/job entrypoints; it requires no LLM for monitoring. AgentTrade plus one scheduled job is the first integration. Propagate job/run/step/request/trace and config version through asynchronous workers and MCP services; distinguish executing service from beneficiary tenant/user. Instrument internal MCP LLM work explicitly. Capture lifecycle, heartbeat and coverage with bounded non-blocking export, deduplication and visible loss. Gateway controls apply only to routed traffic; CLI/web telemetry coverage is capability-dependent. Electron is optional later, not the primary UI.

### yaml configuration optimisation

Manage authorised application YAML using reusable repository, app API and local connector adapters. Preserve YAML as authoritative app configuration, record redacted versions/diffs/audits in tenant-scoped PostgreSQL and correlate runtime usage with the effective prompt/config version. Suggest cheaper compatible models using permitted or synthetic workload evaluations of quality, latency, reliability and total successful-task cost. Show changes, enforce write grants, validate schema/capabilities and source revision, preserve unrelated content, verify runtime activation and support rollback. Read permission does not grant write permission; lower token price alone does not establish equivalent quality. Record optimisation/evaluation cost separately.

### cost provenance and no double counting

Maintain one tenant-scoped ledger with stable source/event/request IDs and parent-child execution links. SDK, OTel and gateway records for the same attempt are correlated, not counted as extra charges; genuine billed retries/fallbacks remain distinct. Parent job/MCP totals roll up unique child charges plus separately evidenced tool fees. Distinguish provider-reported/billed, rate-calculated, subscription fees and estimated API-equivalent value; never sum subscription equivalent value as actual extra spend. Unknown cost/coverage is not zero. Use decimal money with currency, rate/config provenance, requested and served provider/model, and reconciliation evidence. All tenant authorisation comes from validated credentials/membership.

## Acceptance criteria

- On a clean checkout, documented Docker Compose setup starts the independent services; the offline demo shows synthetic jobs and usage without provider credentials. A live provider smoke test is separately documented.
- Responsive React monitoring works at desktop and mobile widths, supports tenant-authorised filtering/drilldown across app/job/run/step/request/MCP/provider/model/source/config version, and connects to AgentDesk.
- All durable product records are stored in PostgreSQL with authenticated tenant ownership. Two-tenant API, worker and database isolation tests cover reads, writes, exports, aggregations and background tasks. Telemetry tags alone never establish identity.
- One AgentTrade scheduled job produces a complete job -> worker/step -> MCP/LLM trace. Per-run cost equals distinct priced attempts; SDK/gateway duplicate delivery does not inflate totals. Parallel executions remain isolated.
- Scheduled-job registration, start/finish/failure events, heartbeat/timeout handling and coverage indicators reveal missed/stuck/disconnected jobs. Bounded telemetry buffering, retry, deduplication and flush-on-exit do not block business jobs; data loss is visible.
- Charges, calculated API cost, subscription fees, estimated equivalent value and unknown costs are distinguishable. Retries/fallbacks and provider routing preserve request identifiers and rate provenance; reconciliation flags differences without overwriting source evidence.
- Authorised YAML connectors inventory prompts/models, associate runtime requests with configuration versions, detect changes, preview schema-validated diffs, evaluate compatible alternatives, apply within granted permissions and verify activation or roll back.
- Budgets, model policies, fallbacks, experiments and quality feedback operate on supported gateway traffic; telemetry-only integrations disclose their control and coverage limits. Optimisation includes its own evaluation costs.
- Each deployable service has its own entrypoint/container, config, health check and restart lifecycle. Cross-service interaction uses versioned contracts; shared libraries contain domain logic and one migration owner controls schema changes.
- Code is minimal and reusable with focused classes/methods, clear public documentation, no duplicated behaviour, explicit errors, environment/config-driven parameters, named parameterised SQL constants and append-only idempotent migrations.
- Apache-2.0 project licensing, dependency notices/license texts as required, README credits, in-app licenses and CI dependency/license checks exist. No LiteLLM enterprise code or prohibited dependency is required for the default install.
- Tenant-scoped AgentDesk and AgentData integrations demonstrate cost per work item/role and natural-language usage queries without unrestricted cross-tenant database access. Secrets remain in env/encrypted secret storage, outside Git and ordinary telemetry.

- A tenant admin registers a previously unknown API, connection and free/paid plan through React, and a wrapped or manually recorded call appears under its API ID without adding provider-specific Dispatcher code.
- A scheduled AgentTrade fixture includes one non-LLM API operation and one LLM request in the same trace; the dashboard shows distinct and combined costs without double counting.
- Two independent quota rules can count all attempts for a rate window while counting only configured successful statuses for billing credits; retries, pagination, batches, cache hits, 429s and ambiguous timeouts follow documented rules.
- Deterministic fixtures verify free, per-request, custom-unit, subscription-with-included-units, tiered/overage and unknown pricing; historical events retain the effective plan version and fixed fees are counted once.
- Per-connection quota windows, budgets, threshold alerts, stale/missing coverage and observed-vs-provider remaining values are visible. Distributed hard enforcement is outside passive monitoring and must not be claimed.
- Cross-tenant API catalogs, telemetry, pricing, exports and plan edits are access-controlled; sensitive bodies, credentials and raw query strings are absent from default telemetry.

- Google and email sign-in work on desktop/mobile; invalid issuer/audience/signature, expired tokens, mismatched state/nonce and replayed email links are rejected. Email sign-in and delivery configuration are documented.
- Verified login alone grants no existing tenant membership. Invite acceptance, tenant selection, owner/admin/member/viewer permissions and removal are tested with two tenants and multiple users. Matching email/domain cannot silently merge accounts or grant membership.
- Tenant SDK key issuance shows the secret once; storage and logs contain no recoverable key. Tenant/app/environment scopes, expiry, rotation and revocation are enforced on every ingestion path.
- An SDK key cannot access human/admin routes or claim another tenant/app. User attribution is labelled verified or app-reported; unverified actor metadata cannot grant access or impersonate a user.
- Logout, revoked sessions, removed memberships and revoked SDK keys cease authorising subsequent requests; asynchronous workers and PostgreSQL pooled connections preserve the verified tenant boundary.

## Delivery sequence

1. Define tenant identity, authenticated attribution, event contracts, PostgreSQL ownership/RLS, monetary semantics, deduplication and service boundaries; retain US10000 and existing child relationships.
2. Scaffold the minimal monorepo/Compose stack, migration ownership, offline demo, licenses and documented environment setup.
3. Implement tenant-isolated ledger, intake and gateway correlation, followed by the lightweight SDK and AgentTrade scheduled-job vertical slice.
4. Deliver responsive React monitoring, job health/coverage, AgentDesk/AgentData connectors and supported CLI/MCP integrations.
5. Implement YAML discovery/version association before controlled changes; add eval-backed recommendations, policies, experiments, rollback and activation checks.
6. Add billing reconciliation, advanced optimisation and optional desktop/browser coverage after the core monitoring flow is verified. Re-estimate delivery after technical spikes; do not promise the original 2–3 week full scope.

The first demonstrable slice is independent services + tenant ledger + SDK + one AgentTrade scheduled run + React drilldown. Identity/isolation, metadata-only capture and attribution are part of that slice. YAML mutation and quality optimisation follow reliable monitoring. Preserve subsequent policies, budget alerts, AgentData/AgentDesk integration, reconciliation and optional browser coverage.

## Tracked work

The existing use case and all 12 original child IDs are retained; six tasks are added, now approved for implementation; completion remains subject to verification.

### FE10000 — Install & first-run setup

Minimal standalone Docker Compose install from one monorepo: independently deployable React web UI, Dispatcher API, background worker, LiteLLM, OTel collector and PostgreSQL. Provide setup wizard, encrypted/env-backed provider credentials, per-app/environment virtual keys, tenant membership and SDK/CLI connection checks. Localhost/private defaults; document authenticated HTTPS access for mobile. Offline synthetic demo requires no provider key. Desktop shell is optional later.

**Verification:** Clean checkout boots using documented configuration; demo shows a job and its usage without external AI calls. A live SDK/gateway and supported CLI telemetry connection each show first-event status. Restarting the worker does not restart the API/UI; gateway/admin/database endpoints are private by default.

### FE10001 — Monitoring: overview, jobs, sessions, users and budgets

Responsive React monitoring is the primary UI. Show tenant-scoped spend/tokens/requests and trends with drilldown by user/service, app/environment, project/work item, scheduler/job/run/step, session, MCP server/tool, provider/model, source and prompt/config version. Show retries, failures, latency, registered schedules, missed/stuck jobs, heartbeats, disconnected sources, budgets/alerts and coverage. Keep billed/reported, calculated, subscription and estimated equivalent values separate. Parent job/tool costs roll up unique child billing events.

**Verification:** Dashboard totals match distinct ledger attempts for the selected tenant/period; duplicate exports and nested MCP rollups do not inflate spend. Concurrent jobs remain separate. Unknown cost and stale coverage are visible. Budget thresholds are configurable; mobile and desktop show usable drilldowns. Job failures and missed-run fixtures appear correctly.

### FE10002 — Control & improvement: YAML configuration, policies and experiments

Add authorised repository/app API/local connectors for each app's YAML prompt/model configuration. Inventory versions and connect them to runtime usage. Detect drift, evaluate cheaper compatible models using permitted or synthetic samples, display cost/quality/latency evidence and proposed diffs, then support permission-controlled application, activation verification and rollback. Keep model allow-lists, routing, fallbacks, budgets, caching, A/B feedback and promote-winner. Gateway controls only routed traffic; OpenRouter is optional. YAML remains authoritative for app configuration; snapshots/audit/eval results live in tenant-scoped PostgreSQL.

**Verification:** Disallowed models are blocked and changes audited. Eval fixtures reject incompatible replacements and show evaluation costs separately. YAML changes validate, preserve unrelated fields/comments where supported, reject stale versions and verify runtime activation. Failed activation supports rollback. Seeded routing verification checks configured weights without a flaky live statistical threshold. Telemetry-only sources disclose control limits.

### FE10003 — AgentDesk, AgentData and application SDK integration

Integrate with AgentDesk identity, tenant membership, projects/work items and role attribution using validated credentials plus per-request context. Provide a small OpenTelemetry-based SDK for app LLM clients and scheduled jobs/workers, starting with AgentTrade. Forward trace context through queues/services/MCP and correlate with gateway records. Provide tenant-authorised Dispatcher MCP tools, AgentData read-only tenant-scoped PostgreSQL connector and llm_usage.yaml semantic model. Keep demo bundle and usage-query examples.

**Verification:** AgentTrade scheduled-job cost matches its distinct request attempts and remains attributable across a worker/MCP boundary. AgentDesk work-item totals match Dispatcher, including mid-session switches. AgentData questions match tenant-scoped SQL totals; another tenant's data is inaccessible. MCP read/write permissions and delegated tenant context are validated.

### FE10004 — Open-source quality, attribution, security and privacy

Apache-2.0 distribution with minimal dependencies and reusable single-purpose classes/methods/modules. Public docstrings and comments explain intent/constraints; explicit errors, config-driven values and named parameterised SQL follow org standards. Include LICENSE, THIRD_PARTY_NOTICES, required upstream license texts, README Built on, in-app licenses and dependency inventory/checks. Use audited supported pinned releases, private admin endpoints, least-privilege tenant isolation, retention and metadata-only default capture. No mandatory LiteLLM enterprise/commercial or prohibited AGPL dependencies. Assess current release advisories at implementation instead of relying on a stale version floor.

**Verification:** CI detects prohibited dependencies/enterprise paths; notices cover every shipped component with version, source and license. Default telemetry stores no prompt/response content or secrets. Two-tenant isolation and retention/export/deletion tests pass. Quickstart and offline demo work without a paid service; dependency pins are checked against current supported/security requirements.

### TA10004 — Scaffold minimal monorepo and independently deployable Compose services

Scaffold UI (React/TypeScript/Vite), Python/FastAPI API, dedicated background worker, LiteLLM gateway, OTel collector and PostgreSQL in one Git repository. Give each service its own entrypoint/container, config, health check and lifecycle. Share contracts/domain code through packages rather than copying or importing another service's internals. One migration owner; separate gateway-owned persistence. Supply Apache-2.0 LICENSE, README, notices, env example, deterministic offline fixtures and demo profile. Use supported pinned images and configurable endpoints/ports; PostgreSQL-backed background coordination avoids a mandatory extra broker.

**Verification:** Clean-checkout Compose/demo smoke test succeeds without provider keys. Each app service starts/restarts independently. API and worker use shared contracts; a single migration job owns application schema upgrades. Data survives container restart. Optional real-provider test records a request; management ports are private by default.

### TA10011 — Tenant-isolated PostgreSQL ledger, execution context and pricing

Store all durable product data in PostgreSQL: tenants/memberships/apps, connections, schedule/job/run/step state, sessions/traces/tool calls, normalised billable attempts, price snapshots, subscriptions, config snapshots/diffs, policies/evals/experiments, audit history and coverage. Use mandatory tenant ownership and tenant-aware constraints/indexes, authenticated API/worker scope and enforced RLS with non-bypass runtime roles. One cluster/shared application schema is the minimal default; dedicated tenant databases are optional future deployment isolation. Separate LiteLLM persistence and access. Preserve app YAML as source, secrets in encrypted/env stores. Correlate SDK/proxy/OTel/provider events using stable IDs and unique tenant/source event keys. Distinguish retries from repeated exports; use decimal money, currency and pricing provenance; unknown costs stay unknown.

Extend the common event/ledger model with resource_kind (llm/api/tool), api_id, connection/account and quota-pool identity, operation/route template, logical operation/attempt IDs, HTTP outcome, observed quota units and billable units. Persist tenant-owned catalog, immutable effective-dated plan/rate versions, quota windows/snapshots, subscription charges, pricing evidence and cost allocations. Keep one pricing/deduplication implementation shared with LLM accounting; do not require model/token fields on general API events. Retain raw measurement evidence separately from derived cost. Scope shared credential pools explicitly and preserve tenant access; never persist raw keys as pool IDs.

Authentication persistence: PostgreSQL stores stable users, provider identity links, tenant memberships/roles, invitations, session/token verifiers, tenant/app/environment service principals, API key verifiers and lifecycle metadata, and auth audit events. Restrict identity tables and credential lookups to the auth boundary; tenant RLS must not rely on unvalidated payload context. Store only hashes of high-entropy SDK and email-link secrets, with public lookup IDs, expiry/revocation and last-used metadata. Keep provider credentials in the separate encrypted/env secret mechanism.

**Verification:** Integration tests with two tenants prove API, DB, workers, exports and joins cannot cross tenant boundaries, including pooled connections and malicious attribution tags. Fixture ingestion covers duplicate/reordered events, concurrent runs, retries/fallbacks, cached usage, missing prices and subscription equivalents. Parent totals sum unique billable attempts. Idempotent migrations and a restore smoke test preserve data and ownership.

- A tenant admin registers a previously unknown API, connection and free/paid plan through React, and a wrapped or manually recorded call appears under its API ID without adding provider-specific Dispatcher code.
- A scheduled AgentTrade fixture includes one non-LLM API operation and one LLM request in the same trace; the dashboard shows distinct and combined costs without double counting.
- Two independent quota rules can count all attempts for a rate window while counting only configured successful statuses for billing credits; retries, pagination, batches, cache hits, 429s and ambiguous timeouts follow documented rules.
- Deterministic fixtures verify free, per-request, custom-unit, subscription-with-included-units, tiered/overage and unknown pricing; historical events retain the effective plan version and fixed fees are counted once.
- Per-connection quota windows, budgets, threshold alerts, stale/missing coverage and observed-vs-provider remaining values are visible. Distributed hard enforcement is outside passive monitoring and must not be claimed.
- Cross-tenant API catalogs, telemetry, pricing, exports and plan edits are access-controlled; sensitive bodies, credentials and raw query strings are absent from default telemetry.

Auth persistence tests cover duplicate provider identity links, tenant-aware membership constraints, key verifier storage without plaintext, revocation, session expiry and cross-tenant lookup/export isolation.

### TA10010 — Responsive React monitoring UI: overview, jobs, sessions and connections

React/TypeScript/Vite web UI primarily for user monitoring on desktop and mobile, using shared AgentDesk/AgentData design tokens. Build Overview, Jobs/Runs, Sessions/Traces, Connections/Coverage, Budgets, Configuration and Licenses views. Support authenticated tenant selection, accessible charts/tables and request-level drilldowns. Config changes call backend connectors; a browser cannot silently edit remote/local YAML or CLI files. Retain optional desktop packaging for later; original mockups are visual reference, not a desktop requirement.

Add API Catalog/Plans admin screens to create and update a new API ID, connection, endpoint/operation matching, quota windows, currency/unit prices, free allowances, tiers/overage, fixed fees and alert thresholds. Show validation and a synthetic pricing preview before publishing an effective-dated revision, with permission checks and audit history. Monitoring filters LLM/API/tool and displays request/quota/billed units, costs, errors, latency and coverage. Link SDK integration instructions to the saved stable ID. No desktop companion is required.

Add Google/email sign-in, logout, explicit authorised tenant switcher, invite/membership management and role-gated SDK key lifecycle screens. Email uses passwordless links as the initial assumption. Only authorised tenant admins may issue/revoke keys; display each new secret once with copy guidance for server-side env/secret storage. Never embed SDK service keys in the React bundle or browser storage.

**Verification:** Production web build passes. Browser checks at mobile/desktop widths cover overview -> job -> request, tenant access, stale/unknown data states and connection onboarding. Totals match tenant-scoped ledger fixtures. Configuration write controls reflect permissions. No provider secrets are sent to the frontend; licenses are reachable.

A newly configured API becomes visible in job/query drilldowns without provider-specific frontend code. Admin-only plan changes are versioned and previewed; unknown and explicitly free prices differ. Mobile/desktop UI validates quota scopes and charging rules and never asks to paste provider credentials into telemetry.

Desktop/mobile auth flows and tenant switching preserve API-enforced permissions; inaccessible tenants/admin actions stay inaccessible through direct API requests. SDK secrets appear only at creation and cannot be retrieved later.

### TA10005 — Tenant-scoped AgentData connector and usage semantic model

Provide least-privilege read-only PostgreSQL access with tenant identity bound to the connector credential/role and enforced views/RLS; never expose an unrestricted shared agentdata_ro credential across tenants. Ship llm_usage.yaml with cost kinds, tokens, calls/attempts, latency, dimensions for tenant/user/service/app/environment/job/run/project/model/provider/tool/source/config version/experiment. Route AgentData LLM work via gateway and SDK context. Keep demo questions and report examples.

**Verification:** At least three usage questions match authorised SQL and UI totals. A second tenant's rows cannot be read even if a query omits or alters its tenant filter. Token/cost categories and rollups avoid double counting. AgentData's own requests appear with tenant, feature and config version.

### TA10003 — Google/email authentication, tenant SDK keys and AgentDesk attribution

Validate AgentDesk identity/session credentials and membership server-side; map tenant/user/service to Dispatcher permissions. OTEL_RESOURCE_ATTRIBUTES supplies stable service/project defaults, while changing work-item/role context travels per request/job. Sync caller-session mappings with effective times so mid-session switches do not rewrite prior attribution. Provide tenant-authorised get_usage/get_session/list_experiments and permission-controlled set_policy tools; show work-item and pipeline-role costs in AgentDesk. Provide a minimal standalone identity adapter for the required Google/email sign-in flows.

Authentication clarification (2026-11-01): Human access supports Google sign-in and verified email sign-in; passwordless email links are the initial design assumption. Resolve users, tenant memberships and roles server-side, including AgentDesk identity integration. SDKs use dedicated tenant-scoped service API keys, preferably separate per app/environment, with only a cryptographic verifier/hash stored in PostgreSQL. The SDK transmits the original random secret over TLS; a stored hash is never a client credential. Keys identify services, not human users. Tenant and permissions come from validated credentials, never telemetry tags.

Use maintained OIDC/session primitives through one identity adapter and shared authorisation module; preserve AgentDesk support. Validate Google tokens server-side and bind identities by issuer+subject. Verify email ownership with single-use expiring links, generic responses and throttling. Explicit authenticated account linking only. Use secure HttpOnly sessions with CSRF protection, configurable lifetime, logout/revocation and role checks. Tenant creation/initial owner provisioning is an explicit controlled flow; joining an existing tenant needs an invitation or authorised membership sync. Define owner/admin/member/viewer capabilities centrally. SDK keys are scoped service principals: ingest-only by default, no dashboard/admin privileges, optional app/environment restrictions, configurable expiration, rotation and immediate revocation. Separate SDK credentials from LiteLLM virtual keys and provider secrets. Keep authenticated principal separate from app-reported user attribution.

**Verification:** An AgentDesk-originated test session and scheduled role run show matching Dispatcher/work-item totals. Mid-session work-item switch splits costs correctly. Spoofed tenant tags or invalid membership fail authorisation; MCP access cannot cross tenants. Credentials never enter logs or prompt content.

- Google and email sign-in work on desktop/mobile; invalid issuer/audience/signature, expired tokens, mismatched state/nonce and replayed email links are rejected. Email sign-in and delivery configuration are documented.
- Verified login alone grants no existing tenant membership. Invite acceptance, tenant selection, owner/admin/member/viewer permissions and removal are tested with two tenants and multiple users. Matching email/domain cannot silently merge accounts or grant membership.
- Tenant SDK key issuance shows the secret once; storage and logs contain no recoverable key. Tenant/app/environment scopes, expiry, rotation and revocation are enforced on every ingestion path.
- An SDK key cannot access human/admin routes or claim another tenant/app. User attribution is labelled verified or app-reported; unverified actor metadata cannot grant access or impersonate a user.
- Logout, revoked sessions, removed memberships and revoked SDK keys cease authorising subsequent requests; asynchronous workers and PostgreSQL pooled connections preserve the verified tenant boundary.

**Implementation:** Implement the common principal/membership/permission contract first, with AgentDesk and Google/email adapters. Add PostgreSQL session and token-verifier storage, invitation lifecycle and SDK key management. Bind every API/MCP/OTel intake path and worker to validated tenant context; protect or keep internal-only any collector/gateway endpoint that could bypass intake. Integrate React and SDK flows, then run isolation and credential-lifecycle tests before live auth confirmation.

### TA10006 — Evidence-backed model policies and first A/B experiment

Configure allowed models and fallback/routing policies through reusable gateway adapters. Use configurable candidates, task tags, seeded assignment and app-provided/eval/AgentData quality feedback rather than fixed model names. Record requested and served model/provider, config version, cost/latency/errors/quality per variant. Compare successful task cost including retries, fees where applicable and evaluation spend. Promote a compatible winner through audited routing or a reviewed YAML change with activation/rollback. OpenRouter is an optional provider route.

**Verification:** Restricted model requests fail clearly; deterministic fixture tests verify variant assignment and fallback attribution. Results include quality and full task cost; incompatible or insufficiently evaluated candidates cannot be labelled proven savings. Promotion is audited and reversible and changes the effective runtime configuration.

### TA10007 — License checks, privacy and minimal-release verification

Add dependency/license inventory and CI checks covering application code, SDKs, containers and bundled assets; reject prohibited licenses and LiteLLM enterprise code. Keep credits, notices and required upstream licenses in sync. Check pinned supported dependency versions against advisories at release; do not treat the old LiteLLM 1.84 floor as sufficient. Private admin routes, encrypted/env secrets, configured egress for authorised providers/MCP/connectors, least-privilege PostgreSQL/RLS and metadata-only defaults. Include clean-checkout/offline demo verification, service health and concise install/test/contributing documentation.

**Verification:** CI catches a prohibited fixture dependency or enterprise path; notices include every shipped third-party component. Default sample traffic leaks no secrets or prompt/response content. Two-tenant and connector-permission checks pass. The documented offline demo and independent service restarts succeed with only the documented prerequisites.

### TA10012 — Reusable LLM/API monitoring SDK and AgentTrade integration

Build a minimal OpenTelemetry-based monitoring SDK, initially for AgentTrade's runtime; add other language SDKs only when a consuming app needs them. Instrument the shared LLM client once and wrap scheduler/job entrypoints. Carry authenticated tenant/app/environment identity plus user/service, job definition/run/attempt/step, trace/request IDs and prompt/config version across asynchronous tasks, queued workers, HTTP and MCP. Export start/finish/failure events, token/latency data and gateway correlation; record actual provider usage when available. Monitoring does not use an LLM. Bounded buffering, configurable retries/backoff, graceful flush, idempotency and observable drop counters must not block business jobs. Optional local spool is encrypted/redacted, bounded, transient and not an authoritative datastore.

Acceptance: One AgentTrade scheduled-job fixture, including a worker boundary, MCP step, concurrent run and charged retry, is visible end-to-end. Totals equal distinct billing attempts. Replayed SDK/gateway events do not inflate cost. Timeout, exporter outage and abrupt termination produce visible coverage gaps without stopping trading jobs. Document minimal integration at the shared client and job boundary; direct bypass calls are identified as uncovered.
Dependencies: TA10004 and TA10011. Do not modify a separate AgentTrade repository until implementation scope/access is established. Detailed spec: documents/output/agentdispatcher-specification.md.

Generalise the SDK boundary to arbitrary API operations: supported HTTP-client instrumentation plus explicit context/wrapper and record-usage interfaces for vendor libraries or custom units. Reuse the same job/trace/export contract for LLM and non-LLM calls. Record attempt-level events with stable API/connection/operation IDs and supplied units, preserve responses and exceptions, avoid implicit retries and duplicated auto/manual spans, and never collect credentials or raw request/response content by default. Admin config owns plan rules; SDK configuration binds local calls to catalog IDs. First fixture combines market-data retrieval and LLM analysis in a scheduled job and also covers a user-query path.

SDK authentication uses a dedicated random tenant service key loaded from the host app's env/secret store; the server stores only a verifier/hash. Prefer one key per app/environment. Do not expose long-lived keys in browser/mobile client code; those clients call an authenticated backend. Reject tenant/app/environment scope mismatches at intake. Distinguish authenticated service principal from app-reported end-user IDs (namespace by tenant/app) and separately verified delegated identity; metadata never grants membership or permissions. Keep SDK keys separate from LiteLLM virtual keys/provider credentials. Document rotation, revocation and redacted export failures.

**Verification:** Replay and automatic/manual overlap do not duplicate calls. A successful, failed, timed-out, retried, paginated, batched and cached operation has explicit semantics. Instrumentation preserves application behaviour during exporter failure. Uninstrumented/out-of-process retries remain documented coverage gaps. New generic APIs need configuration plus SDK binding, not core provider code.

Two-tenant SDK fixtures reject wrong tenant/app, missing/expired/revoked keys and admin-route use; normal telemetry retry/replay handling remains idempotent. A scheduled run authenticates as a service without an invented human user. User-query traces label verified versus app-reported actor identity.

### TA10008 — MCP gateway and external CLI monitoring adapters

Register authorised MCP servers through the gateway, preserve upstream credentials separately, and capture tool/server/caller, failures, latency and trace correlation. Instrument owned MCP services' nested LLM requests; do not infer hidden provider cost from tool invocation count. Provide version/capability-aware Claude Code/Codex onboarding for gateway or telemetry mode and coverage diagnostics. Per-source adapters normalise into shared contracts. A remote collector cannot automatically discover local stdio MCP servers; use an authorised local connector where needed. Optional browser estimation remains later scope.

Acceptance: A fixture client calls an MCP tool that makes multiple LLM calls and displays one correct total with distinct tool charges where supplied. Gateway/SDK duplicates are merged; tenant/upstream credential boundaries hold. Supported CLI fixtures ingest correctly with source and cost confidence; unsupported fields and disconnected sources appear as gaps. Gateway-only controls are not offered for telemetry-only clients.
Dependencies: TA10011, TA10003 and monitoring SDK. Detailed spec: documents/output/agentdispatcher-specification.md.

### TA10009 — YAML configuration connectors, version tracking and reversible updates

Provide a reusable connector interface for authorised Git repositories, app configuration APIs and local files via a connector. Keep existing YAML authoritative; record redacted tenant-scoped snapshots/hashes, prompt/model/parameter inventory, source revision and audit history in PostgreSQL. Associate requests with effective config version. Monitor changes and runtime drift. Validate schema and model capabilities; show exact diffs, enforce least-privilege write grants, use optimistic concurrency, preserve unrelated fields/comments where supported, apply atomically and support rollback. Git-backed changes use a reviewable branch/PR when configured. Verify reload/redeploy activation explicitly; editing a file is not proof of deployment. Never execute YAML as code or persist plaintext secrets.

Acceptance: Fixtures for repository/API/file connectors demonstrate discovery, version attribution, external edit detection, stale-write rejection, restricted writes, valid model changes and failed-activation rollback. Unsupported YAML structures fail clearly rather than being rewritten destructively. Synthetic/permitted evaluations compare quality, latency, successful-task cost and evaluation spend; lower price alone cannot prove equivalence.
Dependencies: TA10011, TA10010 and monitoring SDK; integrates with TA10006. Detailed spec: documents/output/agentdispatcher-specification.md.

### TA10000 — Background job health, coverage and billing reconciliation

Implement the independent Dispatcher worker using shared application contracts and PostgreSQL-backed durable task state/leases. Monitor external app schedules rather than taking ownership of their business schedulers. Store schedule/time zone, expected runs, grace periods, run state, heartbeats, source health and late events. Distinguish missed, stuck, failed, cancelled and completed runs; late telemetry can reconcile earlier provisional states. Run configurable budget alerts, retention, config polling and provider usage reconciliation where credentials/APIs allow. Keep provider charges, rate-derived cost, subscriptions, estimates, fees and unknown values separate; preserve reconciliation evidence and price versions. Worker restart must not duplicate tasks/alerts or cross tenant context.

Acceptance: Deterministic clock/fixture checks cover missed/stuck runs, DST/time zones, overlapping runs, late completion, worker restart and stale connection indicators. Two tenants cannot read or modify each other's jobs or exports. Reconciliation fixtures surface drift without adding aggregate invoices to already-counted request costs. Provider-API unavailability appears as stale/incomplete data. Decimal money and explicit currencies are preserved.
Dependencies: TA10004, TA10011 and monitoring SDK. Detailed spec: documents/output/agentdispatcher-specification.md.

Extend background aggregation/reconciliation to API quota pools and effective-dated plans. Maintain distinct short rate windows and billing-cycle allowances, configurable threshold crossing notifications with deduplication, time-zone/reset handling and late-event corrections. Show provider snapshots versus locally observed remaining allowance with freshness and scope; imports/reconciliation never add already-counted charges twice. Monitoring calls made by Dispatcher itself must also be attributed. No automatic provider probing, retry of business requests or distributed quota enforcement is introduced by passive monitoring.

**Verification:** Fixtures cover multiple apps sharing a credential pool, reset boundaries, duplicate/late events, provider snapshot drift and threshold notification deduplication. Changing prices preserves original historical calculations; any re-rating is explicit/audited. Fixed fees are recorded once and allocated views do not add to actual total.

### TA10001 — Admin API catalog and versioned provider plans

Create tenant-scoped catalog/connection and plan CRUD endpoints with React admin forms. Users register stable IDs for custom APIs, operation/endpoint templates, quota scope/account-key pools, rate/billing windows, reset policy, unit definitions, status-dependent counting, free allowances, subscription fees, per-unit/tiered/overage pricing, currency and thresholds. Persist effective-dated revisions, source/last-verified date, audit and role permissions in PostgreSQL. Validate rules declaratively; no arbitrary scripts, automatic endpoint probes or plaintext keys. Preview synthetic usage charges before publishing. SDK binds calls to IDs; config-only changes cover generic request/unit pricing. Unknown provider terms or counters remain unknown. CoinGecko/Yahoo Finance are example connection names, not guarantees of fixed free tiers or official supported APIs. Dependencies: TA10011, TA10010. Acceptance: a new custom API can be created and metered without code changes; version changes preserve history; pricing preview and cross-tenant/admin-only tests pass.

### TA10002 — Shared API quota and pricing engine with mixed-workload fixtures

Extend shared accounting behind LLM/API adapters to distinguish logical operations, physical attempts, quota consumption and charged units. Implement decimal pricing for explicit free, request/custom-unit, fixed subscription with included units, graduated versus volume tiers and overage plans; unsupported formulas fail explicitly. Quota rules independently specify counted outcomes, unit weights, connection/account/endpoint pool and rolling/fixed/billing windows with reset time zone. Handle refunds/adjustments as evidence-backed entries; aggregate invoices and allocated fixed fees must not double count. Deduplicate retries versus exports, apply effective plan at event time, expose price/coverage uncertainty and provider-reported snapshots separately. Emit threshold alerts with deduplication; monitoring does not guarantee hard quota enforcement across processes. Reuse PostgreSQL worker and SDK, no new service. Dependencies: TA10011, TA10012, TA10000 and API catalog. Acceptance: deterministic fixtures exercise success/error/429/timeout, retry/pagination/batch/cache, overlapping worker runs, late arrivals, plan changes and two tenants. AgentTrade demo combines a custom market-data call and LiteLLM analysis, with per-provider and total run cost matching unique billable events. Synthetic fixture limits/prices are explicitly labelled and do not assert current vendor terms.

## Implementation decisions to verify

- Inspect AgentTrade's actual runtime, common LLM client and scheduler before choosing SDK hooks; do not assume a framework or promise zero code changes.
- Verify AgentDesk's identity/membership contract and select maintained Google OIDC/email/session libraries for the required standalone adapter; configure Google callbacks and email delivery before live smoke tests.
- Validate open-source availability of required gateway features on the selected release; no hidden dependency on enterprise tag reporting or permissions.
- Confirm application YAML schemas, access methods and activation mechanisms for the first connector.
- Select supported pinned package/image versions and review their actual license/notice requirements during implementation.
- Define task-specific quality thresholds and permitted evaluation datasets before claiming replacement quality.
- Re-estimate delivery after these checks; the old 2–3 week estimate is not a commitment.

## References and provenance

- Existing US10000 and design-export user stories (2026-10-19), retained in AgentDesk.
- User clarifications and requested durable engineering rules in this session (2026-10-26).
- [LiteLLM gateway](https://docs.litellm.ai/docs/simple_proxy), [MCP gateway](https://docs.litellm.ai/docs/mcp/), [spend tracking](https://docs.litellm.ai/docs/proxy/cost_tracking).
- [OpenTelemetry context propagation](https://opentelemetry.io/docs/concepts/context-propagation/).
- [LiteLLM OpenRouter integration](https://docs.litellm.ai/docs/providers/openrouter), [OpenRouter routing](https://openrouter.ai/docs/guides/routing/provider-selection).

These references inform the proposed architecture; service behaviour and licensing must be verified against the versions actually selected for release.


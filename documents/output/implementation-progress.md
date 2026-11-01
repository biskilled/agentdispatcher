# US10000 implementation progress

First implementation slice, 2026-11-01. Approval promoted the original AI IDs to US10000, FE10000–FE10004 and TA10000–TA10012. Requirements in agentdispatcher-specification.md remain the full target; this file describes actual implementation coverage.

## Current implementation update (2026-11-01)

- LiteLLM is now connected through managed virtual keys and OSS Python callbacks. [CI run 41360357236](https://github.com/biskilled/agentdispatcher/actions/runs/41360357236) passed the real container checks: two-tenant scope, streaming accounting, model restrictions and immediate revocation. Upstream key aliases use unique internal IDs, avoiding tenant name collisions. Full MCP/CLI/OTel and duplicate-source correlation are still open.
- AgentData now has per-tenant PostgreSQL read-only credentials bound to `session_user`, an RLS-protected view, Cube model, provisioning/rotation/revocation and SQL/dashboard parity checks. Live AgentData import and its own LLM call instrumentation remain open.
- YAML file/API/Git connectors, redacted PostgreSQL snapshots, reviewed scalar changes, optimistic concurrency, activation evidence and file/API rollback are implemented with four passing connector/workflow tests. Git produces an unpushed review branch without changing the checkout. Source polling, evaluation-backed recommendations, Git publishing/rollback and runtime drift reports remain open.
- Current local verification: 42 backend/SDK/PostgreSQL tests pass. Desktop/mobile browser flows pass for catalog, SDK keys, schedule registration/disable, budget creation, empty configuration setup and the LLM-key form. Worker startup/health/shutdown and React build pass; overview screenshots reviewed at both sizes. Connected-source browser editing still needs a dedicated fixture.

- Added tenant invitations, membership administration, concurrent last-owner protection, app view grants, verified-user delegation and recent-login Google linking. OAuth state is single-use in PostgreSQL. Eight full callback tests exercise locally signed identity tokens and invalid issuer/audience/signature/expiry/nonce/state/missing-token cases. Live Google and SMTP still require deployment configuration.
- Added API/account/connection/operation pools, subscriptions and included-unit overage, graduated/volume/token pricing, explicit quota outcome rules, rolling/calendar windows, time zones and deduplicated threshold alerts. Admin forms provide connection revisions and synthetic pricing previews. Original event prices remain immutable; cumulative tier allocation uses arrival order within the event-time billing period.
- Added common filtered reporting for app/environment/provider/model/source/user/session/project/work item/job/config/API and time ranges, daily trends, dimension breakdowns, pagination and original-attempt evidence.
- Added HTTPX sync/async monitoring transports, request-scoped metadata, credential-free queue context propagation and short-lived user delegation headers.
- Added persisted external schedules, expected occurrences, late-run reconciliation, worker leases and budget configuration. Fixed fees, explicit refunds and imported provider statement comparisons remain separate from original request totals. Provider statements never become new charges.
- Verification: 36 PostgreSQL/SDK/OIDC tests passed; React TypeScript/production build passed. Desktop and mobile Playwright flows passed including synthetic pricing preview/publication and scoped key lifecycle. New schedule/budget screens build successfully; their browser interaction checks are still pending. Independent worker startup/health/shutdown passed before the latest schedule additions.
- All remaining integrations, release work and full-item acceptance still need completion. This update is not a claim that the entire use case is finished.

## Implemented in the first slice

- Shared Python package, FastAPI service, standalone worker, React/Vite UI, separately installable Python SDK, Compose definitions and a sole migration job.
- PostgreSQL identity store and tenant ledger; separate auth/runtime grants, forced RLS on tenant data, runtime bypass-role rejection, transaction-local scope and tenant-aware constraints.
- Email login/token consumption, secure session cookies, CSRF origin checks, Google OIDC routes via Authlib, explicit Google-link endpoint, operator-only initial owner provisioning.
- Admin-created per-tenant/app/environment SDK keys with hashes only, expiration, immediate revocation, scoped metadata and audit entries.
- Metadata-only event intake, atomic batch scope validation, stable-event replay deduplication, conflicting-evidence rejection, distinct retry attempts, exact decimal cost serialization.
- API catalog with immutable effective versions for unknown/free/per-unit prices; configured status-based billing. Other formulas reject rather than silently approximating.
- Job start/terminal/heartbeat events, concurrent SDK contexts, out-of-order protection and tenant-scoped stale-run detection.
- Responsive overview, recent activity, job runs, API pricing forms, key lifecycle, login and license notices. Synthetic seeded workload traverses SDK → HTTP intake → PostgreSQL → UI.

## Verification evidence

- PostgreSQL integration + SDK suite: 13 passed against an isolated PostgreSQL 15.17 instance. Includes no-scope/cross-tenant RLS reads, identity-table denial, batch atomicity, concurrent replay, changed evidence, token replay, logout, CSRF, expiry/revocation, membership changes, cost history/unknowns, job ordering, no automatic Google/email linking and exporter failure behaviour.
- Independent worker process startup, health command and shutdown passed; the API remained ready. The standalone SDK wheel built successfully with its license included.
- React production build and TypeScript checking passed.
- Playwright end-to-end checks passed at desktop 1440×1000 and mobile 390×844, including actual tenant dashboard data and issuing/revoking SDK keys. Screenshots visually reviewed.
- Runtime dependency notices include 32 Python/JavaScript packages with original license texts. Frontend dependency audit reported no vulnerabilities at install time; this is not a comprehensive release security audit.
- [GitHub CI run 41299724331](https://github.com/biskilled/agentdispatcher/actions/runs/41299724331) passed the application job and Compose build/startup, synthetic SDK demo, worker restart and API readiness checks for runtime commit 7233ae6. Docker remains unavailable locally. Optional gateway/collector profiles and database restart/backup/restore checks remain unverified.
- No live Google or SMTP credentials were supplied. Auth routes and local email-token/session flows exist; real Google login, actual email delivery and the full OIDC negative-case matrix remain unverified. Upstream Authlib/Starlette emit HTTPX deprecation notices; migration to their newer HTTP client integration should be assessed before release.

## Remaining approved scope

| Item | Remaining work |
| --- | --- |
| TA10004 / FE10000 | Database persistence/restore and optional integration-profile checks, guided setup and live connection verification |
| TA10003 | AgentDesk identity/membership adapter and live provider verification; existing standalone identity/access flows now tested |
| TA10011 | Gateway/provider correlation, exports/retention/deletion/restore, full durable entities and broader isolation coverage |
| TA10012 | Instrument the real AgentTrade shared client/scheduler and coverage diagnostics; HTTP hooks and explicit queue context now implemented |
| TA10010 / FE10001 | Browser checks for new budget/schedule screens and full integration connection coverage |
| TA10001 / TA10002 | Full end-to-end mixed AgentTrade/LiteLLM workload and final catalog acceptance review |
| TA10000 | Retention/config polling jobs, live provider refresh integrations, and final worker acceptance review |
| TA10008 / FE10003 | LiteLLM virtual-key/billing adapter, MCP and CLI adapters, authenticated OTel intake |
| TA10005 | AgentData tenant-scoped connector and semantic model |
| TA10009 / FE10002 | YAML inventory/connectors/versioning, reviewed writes, activation checks and rollback |
| TA10006 | Evaluation-backed model alternatives, routing policies and experiments |
| TA10007 / FE10004 | Container/dev-tool notices, full dependency/license/security checks, release audit and end-to-end installation validation |

No work item is claimed complete merely because a slice exists. LiteLLM now sends calculated usage to accounting; provider invoice verification is separate. The OTel collector is diagnostic only. Quotas are evaluated for monitoring and alerts, without hard distributed enforcement.

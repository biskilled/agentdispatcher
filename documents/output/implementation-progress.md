# US10000 implementation progress

First implementation slice, 2026-11-01. Approval promoted the original AI IDs to US10000, FE10000–FE10004 and TA10000–TA10012. Requirements in agentdispatcher-specification.md remain the full target; this file describes actual implementation coverage.

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
- Docker is unavailable on this machine: Compose image builds, restart/persistence checks and optional gateway/collector profiles have not been executed. CI smoke definitions are supplied but not yet reported as passing.
- No live Google or SMTP credentials were supplied. Auth routes and local email-token/session flows exist; real Google login, actual email delivery and the full OIDC negative-case matrix remain unverified. Upstream Authlib/Starlette emit HTTPX deprecation notices; migration to their newer HTTP client integration should be assessed before release.

## Remaining approved scope

| Item | Remaining work |
| --- | --- |
| TA10004 / FE10000 | Compose verification, guided setup and live connection verification |
| TA10003 | Invitations/membership administration, owner invariants, granular view grants, secure account-link reauthentication UX, AgentDesk adapter, full OIDC tests and live providers |
| TA10011 | Gateway/provider correlation, exports/retention/deletion/restore, full durable entities and broader isolation coverage |
| TA10012 | Instrument the real AgentTrade shared client/scheduler, HTTP hooks, cross-process propagation and coverage diagnostics |
| TA10010 / FE10001 | Period/dimension filtering, session/request drilldown, trends, budgets, view grants and full connection coverage |
| TA10001 / TA10002 | Connection/account pools, quota evaluation, thresholds, tiers/subscriptions/included units, full plan audit and preview |
| TA10000 | Schedule registry, missed runs, task leases, budget/retention/config jobs and billing reconciliation |
| TA10008 / FE10003 | LiteLLM virtual-key/billing adapter, MCP and CLI adapters, authenticated OTel intake |
| TA10005 | AgentData tenant-scoped connector and semantic model |
| TA10009 / FE10002 | YAML inventory/connectors/versioning, reviewed writes, activation checks and rollback |
| TA10006 | Evaluation-backed model alternatives, routing policies and experiments |
| TA10007 / FE10004 | Container/dev-tool notices, full dependency/license/security checks, release audit and end-to-end installation validation |

No work item is claimed complete merely because the initial slice exists. LiteLLM is the planned main LLM gateway; its optional Compose service is not yet connected to accounting. The OTel collector is diagnostic only. Quota fields are persisted, not enforced or evaluated. All such boundaries are disclosed in the README and relevant UI.

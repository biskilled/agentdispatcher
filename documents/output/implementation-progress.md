# US10000 implementation progress

Updated 2026-11-02. The approved specification remains the target. This document distinguishes implemented behaviour from remaining acceptance work; the full use case is not yet complete.

## Implemented and verified

- A Python/FastAPI API, independent worker, React/TypeScript mobile dashboard, separately installable monitoring SDK and PostgreSQL ledger share reusable application services. Compose also provides optional LiteLLM, collector and MCP services.
- PostgreSQL enforces tenant isolation with forced RLS, separate auth/runtime grants and transaction-local scope. Human sessions, invitations, live membership/app grants, owner safeguards and scoped SDK keys have integration tests. SDK secrets are displayed once and stored only as hashes.
- Google OIDC and passwordless email use explicit identity linking, single-use state/tokens, CSRF protection and revocable sessions. Signed-token callback fixtures exercise issuer, audience, signature, expiry, nonce and state rejection. Live Google and SMTP verification still needs configured deployment credentials.
- AgentDesk has an explicit identity adapter, tenant binding and personal account linking. Effective-time session context preserves historical work-item/role attribution. The sibling AgentDesk identity endpoint patch and its verification harness are included under `integrations/agentdesk`; deployment remains separate.
- The optional official-SDK MCP service exposes `get_usage`, `get_session`, `list_experiments` and `set_policy`. Dedicated hashed grants remain tied to the human session and current membership; policy changes additionally require explicit consent and a live admin role. This control service is separate from monitoring arbitrary MCP providers.
- LiteLLM uses managed virtual keys and OSS callbacks. Real-container CI verifies tenant separation, streaming accounting, model restrictions, immediate revocation and policy activation/rollback against synthetic provider responses. [CI 41366473576](https://github.com/biskilled/agentdispatcher/actions/runs/41366473576) passed.
- API catalog versions support free/unknown/unit/token/subscription/tier pricing, custom units, multiple quota windows, shared pools and historical audit. Accounting distinguishes physical attempts, logical operations, quotas and charges. Provider statements and adjustments remain separate from original request totals.
- Registered external schedules, expected runs, heartbeats, late-run reconciliation, worker leases, budgets and threshold alerts monitor application schedulers without running their business jobs.
- Model policies support permitted aliases, declared capabilities, fallbacks and deterministic experiments. Promotion requires quality, latency, sample, coverage and successful-task cost checks, including retries and evaluation spend. Immutable promotion evidence and rollback are retained. Passing gates is not labelled statistical proof of savings.
- AgentTrade's actual shared provider clients and scheduler entry points are instrumented. Its synthetic integration harness exercises two tenants, multiple jobs, provider failures and exact dashboard totals without trading or paid API calls. External regression tests passed.
- AgentData has per-tenant read-only PostgreSQL credentials bound to `session_user`, RLS-protected views, a Cube model and credential lifecycle/SQL-dashboard parity tests. Live AgentData import and its own LLM instrumentation remain outstanding.
- YAML file/API/Git connectors preserve safe scalar changes, comments and unrelated fields. PostgreSQL retains redacted snapshots and reviewed diffs. Optimistic concurrency, source-permission fingerprints, activation evidence and file/API rollback are tested. Git currently creates an unpushed review branch.
- React provides reporting filters, trends, attempts, schedules, budgets, catalog, keys, AgentDesk linking, configurations, policies, experiments and tool access. Desktop/mobile browser tests exercise the principal administration flows. Runtime license texts are bundled and shown in the UI.

## Verification

The previous committed baseline passed 55 backend/SDK/PostgreSQL tests, two desktop/mobile browser tests, three sibling AgentDesk identity tests, React type checking/build and GitHub's real Compose/LiteLLM checks. MCP adds three backend grant-lifecycle tests and two official-SDK protocol/HTTP checks. The current expanded suite and MCP container check are being verified before that change is closed out.

Docker is unavailable on this workstation, so container validation runs in GitHub CI. Synthetic provider fixtures verify the integrations without spending provider credits. No live Google/SMTP login or deployed sibling identity endpoint is claimed verified.

## Remaining acceptance work

| Item | Remaining work |
| --- | --- |
| TA10001 | Implemented and in review: custom API catalog, immutable plans, multi-window quotas and audit |
| TA10006 | Implemented and in review: policy/experiment evidence, runtime activation and rollback |
| TA10003 | Finish MCP container verification and configured live Google/email/AgentDesk checks |
| TA10004 / FE10000 | Guided setup, connection diagnostics, database persistence/backup/restore and optional-profile installation checks |
| TA10011 | Cross-source physical-attempt correlation; export, retention, deletion and restore |
| TA10012 | Queue/MCP instrumentation, mixed-source correlation and complete coverage diagnostics |
| TA10010 / FE10001 | Full connection/trace coverage and connected YAML browser editing fixtures |
| TA10002 | Mixed SDK/gateway/OTel accounting without duplicate physical charges |
| TA10000 | Configuration polling/drift, retention work and provider refresh acceptance |
| TA10008 | Arbitrary MCP monitoring gateway, external CLI adapters and authenticated OTel intake |
| TA10005 | Live AgentData model import and its own LLM-call instrumentation |
| TA10009 / FE10002 | Source polling/runtime drift, Git publish/rollback and evaluation-backed YAML suggestions |
| TA10007 / FE10004 | Container/development notices, dependency/security checks and release installation audit |

Quotas currently provide monitoring and alerts, not distributed hard enforcement. The collector is diagnostic until authenticated intake is connected. Completed items go to human review; parent features remain open until their full acceptance criteria are met.

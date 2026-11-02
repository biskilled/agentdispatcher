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
- YAML file/API/Git connectors preserve safe scalar changes, comments and unrelated fields. PostgreSQL retains redacted snapshots and reviewed diffs. Worker polling and per-instance loaded-version heartbeats expose drift, failures and stale/missing evidence. Git writes use deterministic review branches, optional publication to an approved named remote, and a new review branch for rollback. Evaluated suggestions require the exact configuration version and retain their evidence with the reviewed diff. Activation remains distinct from file writes or branch publication.
- React provides reporting filters, trends, attempts, schedules, budgets, catalog, keys, AgentDesk linking, configurations, policies, experiments and tool access. Desktop/mobile browser tests exercise the principal administration flows. Runtime license texts are bundled and shown in the UI.

## Verification

The current suite passes 61 backend/SDK/PostgreSQL tests, plus two official-SDK MCP checks. Two dashboard and two connected-YAML browser checks cover desktop/mobile; the latter verifies actual edits, failed activation and rollback while preserving comments and private prompt text. Three sibling AgentDesk identity checks and React type checking/build also passed. [CI 41368270202](https://github.com/biskilled/agentdispatcher/actions/runs/41368270202) passed the separate MCP container, real PostgreSQL and LiteLLM policy activation/rollback checks. Git publishing/rollback tests use a local bare fixture remote without contacting a real repository.

Docker is unavailable on this workstation, so container validation runs in GitHub CI. Synthetic provider fixtures verify the integrations without spending provider credits. No live Google/SMTP login or deployed sibling identity endpoint is claimed verified.

## Remaining acceptance work

| Item | Remaining work |
| --- | --- |
| TA10001 | Implemented and in review: custom API catalog, immutable plans, multi-window quotas and audit |
| TA10006 | Implemented and in review: policy/experiment evidence, runtime activation and rollback |
| TA10003 | Configured live Google/email/AgentDesk checks; MCP container verification passed |
| TA10004 / FE10000 | Guided setup, connection diagnostics, database persistence/backup/restore and optional-profile installation checks |
| TA10011 | Cross-source physical-attempt correlation; export, retention, deletion and restore |
| TA10012 | Queue/MCP instrumentation, mixed-source correlation and complete coverage diagnostics |
| TA10010 / FE10001 | Full connection/trace coverage; connected YAML browser editing fixtures now pass |
| TA10002 | Mixed SDK/gateway/OTel accounting without duplicate physical charges |
| TA10000 | Retention work and provider refresh acceptance; configuration polling/drift implemented |
| TA10008 | Arbitrary MCP monitoring gateway, external CLI adapters and authenticated OTel intake |
| TA10005 | Live AgentData model import and its own LLM-call instrumentation |
| TA10009 / FE10002 | Connector, polling/drift, Git publish/rollback and evaluated YAML workflows implemented; final verification/review underway |
| TA10007 / FE10004 | Container/development notices, dependency/security checks and release installation audit |

Quotas currently provide monitoring and alerts, not distributed hard enforcement. The collector is diagnostic until authenticated intake is connected. Completed items go to human review; parent features remain open until their full acceptance criteria are met.

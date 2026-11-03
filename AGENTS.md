# Org Standards
_Tenant-wide — applies to every project. Admin-managed; injected into every project's CLAUDE.md._

## Code style
- Write clean, readable code; match the surrounding file's style, naming, and comment density.
- Prefer small, single-purpose, well-named methods; favour clear object-oriented structure.
- **Do not duplicate code** — extract shared logic into a reusable function/module. One source of truth per behaviour.
- Keep functions short; return early; avoid deep nesting.
- Handle errors explicitly — never fail silently (no bare `except: pass` on real failures).

## No hardcoded parameters
- No hardcoded URLs, hosts, ports, file paths, secrets, or magic numbers in code.
- Read them from config / environment (one knob, e.g. `BACKEND_URL`) so changing them is a single edit.
- Secrets never go in source or git-tracked config — use the encrypted secret store / env.

## SQL
- Put SQL as named constants (`_SQL_*`) **at the top of the file**, not inline in functions.
- Always use parameterised queries (`%s` placeholders) — never string-format user input into SQL.
- Table naming: `mng_*` = management/tenant tables, `mem_*` = memory, `mem_mrr_*` = raw mirror events. snake_case columns.
- Migrations are idempotent (`IF NOT EXISTS`, `ON CONFLICT …`) and appended to the migrations list — never edited in place.

## Comments
- Write simple, clear comments that explain **why**, not what the code already says.
- A short docstring on each public function: what it does + non-obvious constraints.
- Remove dead code and stale comments rather than leaving them.

## Conventions
- Config-driven over hardcoded; single source of truth over copies.
- Validate at the boundary; trust internal callers.
- Prefer composition and clear data flow over clever one-liners.

## Shared skills
_Auto-filled from the tenant's available skills._

- **developer** (both) — Execute a coding task end-to-end the way a senior engineer would, using the Claude API directly — no CLI install required. Project-aware via AgentDesk memory and work items; loads the use case and prior art, makes the smallest correct change, verifies it, and reports back. This is the built-in starter skill every project ships with.
- **intake** (both) — Turn design / spec / PRD documents into tracked use cases and work items in AgentDesk, then hand off to solve. Use this whenever the user wants to plan a project from documents, "process my design docs", "build from my spec", turn a PRD or design doc into tasks/use cases, intake requirements, or "set up the backlog from my docs". Reads the project's document folder, maps each loose doc to one use case with its work items, creates them in AgentDesk, and writes a tracked use-case MD (embedding the source verbatim) into use_cases/ WITHOUT ever moving or deleting the original doc. Do NOT use for editing code directly (use the build/solve skill) or for non-planning requests.
- **solve** (both) — The build skill — gets work done at any SCOPE: a single item, one use case, all open use cases, or a direct task you type. Triggers on "solve", "build", "implement", "fix", "clear the backlog", "/solve". For each item it implements the smallest correct change (using the developer engine / work-item pipeline under the hood), verifies it, records the result, and updates status + score. Stops an item once its score is high enough, ends the run when the scope is complete (or the iteration budget is hit), and leaves the final "done" to human approval.
- **web-stack** (both) — Default build conventions for a WEB / APP project: Node.js (Express) on the server, React on the client, and TypeScript throughout. Use when writing, reviewing, or scaffolding a web_app or mobile project. An explicit project override takes precedence.
- **anthropics/skills** (cli) — Official Anthropic Agent Skills — incl. the production pptx skill: pptxgenjs deck creation with validated gotchas, template layout-mapping (thumbnail grids), OOXML editing, deck validator. The best-of-breed engine for deck-generator to orchestrate. · https://github.com/anthropics/skills
- **DietrichGebert/ponytail** (cli) — Makes your AI agent think like the laziest senior dev. The best code is the code you never wrote. · https://github.com/DietrichGebert/ponytail
- **pragmar/mcp-server-webcrawl** (backend) — web crawl MCP · https://github.com/pragmar/mcp-server-webcrawl

## Org rules — always apply
_🌐 = all tenants (platform) · 🏢 = this tenant. Managed in Settings/Admin._
_When one of these rules shapes an action or answer, SAY SO briefly — e.g. “per org rule ‘session start checks’ …” — so rule usage is visible._

- 🏢 **session start checks**: Always check that all hooks are running when you start a session, and make sure you are connected to AgentDesk.
- 🏢 **node_modules folder**: Always store node_modules under /Users/user/Documents/node_modules folder (linked folder) and venv under /Users/user/Documents/venv

<!-- Last updated: 2026-11-03 18:34 UTC -->
# agentdispatcher
_2026-11-03 18:34 UTC | Memory synced: 2026-11-03_

## Recent Work
- [deployment] Railway production instance running with PostgreSQL 17.11+pgvector 0.8.7; six services deployed and operational
- [task] Environment variable configuration documentation for each service (UI, API, worker, scheduler, LiteLLM, OTel)
- [task] Service health checks, billing reconciliation and background job coverage validation
- [feature] Live authentication integration (Google OAuth, email sign-in) awaiting Railway credential configuration
- [bug] Upstream security vulnerabilities in LiteLLM and collector resolved via dependency backport and minimal collector rebuild
- [testing] 96+ tests and full integration CI passing; zero High/Critical security findings in container scans

## Stack & Architecture

- **gateway**: LiteLLM proxy
- **observability**: OpenTelemetry collector
- **database**: PostgreSQL 17.11 with pgvector 0.8.7
- **backend_runtime**: Python 3.12 with FastAPI
- **ui_framework**: React + TypeScript + Vite
- **auth_integration**: AgentDesk token, Google OAuth, email, SDK hash keys per tenant
- **deployment**: Docker Compose with 6 services
- **deployment_platform**: Railway
- **license**: Apache 2.0
- **key_management**: Virtual keys per team/app with LiteLLM settings
- **semantic_layer**: AgentData read-only connector (agentdata_ro role, llm_usage.yaml)
- **monitoring_sources**: OTEL_RESOURCE_ATTRIBUTES for project/work-item/job attribution
- **api_spec**: usage_event schema (ts, user, key, team, project, work_item, client, provider, model, api_id, quota, cost)
- **ci_checks**: pip-licenses/license-checker blocking AGPL and commercial dependencies
- **email**: SMTP via Python smtplib

## Key Architectural Decisions

- Core architecture: LiteLLM proxy + OTel collector + PostgreSQL ledger + React web UI (browser-first, no Electron desktop required)
- Open-source licensing: Apache 2.0 for core, with THIRD_PARTY_NOTICES.md and CI license checks (blocking AGPL, commercial)
- Usage tracking: normalised usage_event ledger capturing timestamp, user, key, team, project, work_item, client, provider, model, with pricing attached
- AgentDesk integration: session→project/work-item attribution via OTEL_RESOURCE_ATTRIBUTES (agentdesk.project, agentdesk.work_item)
- AgentData integration: read-only semantic model (llm_usage.yaml) consumed by AgentData for cross-tenant analytics
- Model governance: allow-lists per virtual key/team/app, force-model rules, weighted routing by task tag or priority
- UI monitoring dimensions: breakdown by client, provider, model, source, with Overview KPIs and per-session drill-down
- Multi-tenant support: isolated usage ledgers per tenant with team-level key management and budget policies
- Mobile-first monitoring: React web app usable on desktop and mobile, shared design tokens with AgentDesk
- Agent instrumentation: small agents (e.g., AgentTrade) integrate via OTEL_RESOURCE_ATTRIBUTES to tag scheduled/hard-to-monitor LLM jobs
- API monitoring: general-purpose SDK for tracking any API usage (LLM, CoinGecko, Yahoo Finance, paid/free) with tenant-scoped catalog and pricing configuration
- Authentication: AgentDesk token (identity/session/membership), Google OAuth, user email, SDK dedicated hash keys per tenant; credentials via environment variables for deployment
- Deployment: six independently deployable services (UI, API, background worker, scheduler, LiteLLM proxy, OTel collector) in single docker-compose stack with PostgreSQL 17.11+pgvector
- Security hardening: pip-licenses/license-checker CI step, OTEL attribute validation, read-only AgentData role, least-privilege tenant isolation
- A/B experiments: routing policies support weighted model variants for experimentation

## Active Features

- `US10000` `AgentDispatcher — open-source LLM gateway and API usage monitoring` [review] — AgentDispatcher is an Apache-2.0 open-source, self-installable app in the AgentDesk ecosystem. A res
  _AC: - On a clean checkout, documented Docker Compose setup starts the independent services; the offline demo shows synthetic jobs and usage without provid_
- `FE10004` `Open-source quality, attribution, security and privacy` [review] — Apache-2.0 distribution with minimal dependencies and reusable single-purpose classes/methods/module
- `FE10003` `AgentDesk, AgentData and application SDK integration` [review] — Integrate with AgentDesk identity, tenant membership, projects/work items and role attribution using

---
_Auto-generated by AgentDesk memory system. Run `/memory` to refresh._
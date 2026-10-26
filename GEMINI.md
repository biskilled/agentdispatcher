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

<!-- Last updated: 2026-10-25 14:18 UTC -->
# agentdispatcher
_2026-10-25 14:18 UTC_

Self-installable, open-source (Apache 2.0) LLM gateway + usage ledger. Captures every LLM request and tool call across Claude Code, Codex, web chat and own apps (AgentData, AgentDesk) via two collectors — LiteLLM proxy for traffic we can route (metered) and an OpenTelemetry collector for CLI subscri

## Structure

- agents/
- caller/
- config/
- core/
- data/
- memory/
- qbr/
- routers/
- scripts/
- templates/
- tests/

## Stack & Architecture

- **gateway**: LiteLLM
- **observability**: OpenTelemetry (collector)
- **database**: PostgreSQL
- **container_orchestration**: Docker Compose
- **license**: Apache 2.0
- **desktop_ui**: Electron + Vite
- **backend_framework**: TBD (core dispatcher)
- **auth_integration**: AgentDesk session tokens + OTEL_RESOURCE_ATTRIBUTES
- **semantic_layer**: llm_usage.yaml (AgentData connector)
- **ci_checks**: pip-licenses / license-checker
- **routing**: LiteLLM key settings (model allow-lists, weighted routing)
- **monitoring**: Custom overview/sessions/users/budgets dashboard
- **ledger_schema**: usage_event (ts, user, key, team, project, work_item, client, provider, model, cost)
- **backend**: Python / FastAPI
- **scheduler**: Dedicated Python / FastAPI service

## Key Architectural Decisions

- Use LiteLLM as the core gateway layer for LLM provider abstraction and routing
- Postgres as authoritative ledger for normalized usage_event records with full attribution chain
- OpenTelemetry for distributed tracing and OTEL_RESOURCE_ATTRIBUTES as primary session context carrier
- AgentDesk integration via session→project/work-item attribution through OTEL_RESOURCE_ATTRIBUTES (not direct API)
- Apache 2.0 license with explicit AGPL/commercial exclusions in CI license check
- Model policies enforced via LiteLLM key settings per virtual key/team/app (no separate policy engine initially)
- Desktop monitoring UI built with Electron + Vite using shared AgentDesk/AgentData token palette (light/dark theme)
- Read-only agentdata_ro Postgres role for AgentData semantic connector (llm_usage.yaml)
- Docker Compose stack as install/first-run mechanism (LiteLLM proxy, OTel collector, Postgres, Dispatcher core)
- Usage event pricing and cost calculation computed at ledger insert time (normalized schema, multi-provider)
- A/B experiment routing via weighted model distribution per key/team
- Three-tier monitoring: overview KPIs, client/provider/model breakdowns with source labels, per-session drill-down
- In-app licenses screen + THIRD_PARTY_NOTICES.md + README 'Built on' for open-source attribution
- No custom auth layer; rely on LiteLLM key management + AgentDesk session validation via OTEL context

---
_Auto-generated by AgentDesk memory system. Run `/memory` to refresh._
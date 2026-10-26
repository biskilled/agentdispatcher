# agentdispatcher
_Last updated: 2026-10-25_

Self-installable, open-source (Apache 2.0) LLM gateway + usage ledger. Captures every LLM request and tool call across Claude Code, Codex, web chat and own apps (AgentData, AgentDesk) via two collectors — LiteLLM proxy for traffic we can route (metered) and an OpenTelemetry collector for CLI subscription logins (reported) — plus an optional browser extension (estimated). Normalises everything into one usage_event ledger in Postgres. Goal 1: monitoring per user/session/project/model/provider/tool. Goal 2: improvement via model policies, routing/fallbacks, A/B experiments with a quality signal, and savings suggestions. Ships with a local desktop UI (AgentDesk theme), an MCP server, AgentDesk work-item attribution, and an AgentData connector + semantic model. Full source attribution for all reused open-source components. Full stories: docs/USER_STORIES.md (DSP-01..DSP-50). Mockups: mockups/agentdispatcher-mockups.html.

## Goals

- Tal tracks all personal LLM usage and cost (Claude Code, Codex, Grok, web, AgentData, AgentDesk) in one place within 2–3 weeks
- AgentData can query LLM usage/cost per project, tenant, user and model in natural language
- Usage can be steered: per-user/app model policies, routing, fallbacks and A/B experiments
- AgentDesk shows AI cost per work item and per pipeline role
- Organisations can download and install it standalone (docker compose or desktop app) with clear open-source attribution and secure defaults

## Feature map

- **Install & first-run setup** — docker compose stack (LiteLLM proxy, OTel collector, Postgres, Dispatcher core, UI) plus desktop app; setup wizard; provider keys; virtual keys per user/app; one-click Connect for Claude Code (gateway or telemetry mode), Codex and SDK apps. Stories DSP-01..04.
- **Monitoring: overview, sessions, users, budgets** — Overview KPIs and breakdowns by client/provider/model with source labels (metered/reported/estimated); sessions explorer with per-step timeline and tool calls; users & teams table; budgets with alerts; subscription value. Stories DSP-10..16.
- **Control & improvement: policies, routing, A/B experiments** — Model allow-lists per key/team/app, force-model rules, routing by task tag or prompt size, fallback chains, caching, A/B experiments with quality score from a feedback API or AgentData validation, promote-winner, savings suggestions. Stories DSP-20..24.
- **AgentDesk & AgentData integration** — AgentDesk: session→project/work-item attribution via OTEL_RESOURCE_ATTRIBUTES and caller-session mapping sync, AI cost on work items, pipeline cost per role, MCP tools (get_usage, get_session, list_experiments, set_policy). AgentData: read-only connector + shipped llm_usage.yaml semantic model; AgentData's own LLM calls routed through the gateway with tenant/feature tags; demo bundle. Stories DSP-30..35.
- **Open-source attribution, security and privacy** — THIRD_PARTY_NOTICES.md, README 'Built on', in-app licenses screen, CI license scan blocking AGPL/commercial and LiteLLM enterprise/; pinned versions, minimum LiteLLM ≥1.84 (2026 CVEs), internal-only admin routes, egress allow-list, least-privilege DB roles; content capture off by default with retention. Stories DSP-40..42.

## Decisions

- Use LiteLLM (MIT core) as the gateway because policies, routing and A/B require being in the request path; OpenLIT is observe-only and Portkey's open-source future is uncertain after its Palo Alto Networks acquisition
- Bifrost not used for now (Go codebase adds structural overhead)
- Add an OpenTelemetry collector for Claude Code/Codex on subscription login, which cannot be proxied
- Never use LiteLLM enterprise/ code; project license Apache 2.0 with THIRD_PARTY_NOTICES.md
- Run LiteLLM hardened: ≥1.84, pinned digests, internal-only admin, egress allow-list (2026 supply-chain incident and CVEs)
- No Grafana (AGPL); ship own UI in the AgentDesk theme
- Every cost is labelled metered / reported / estimated
- Project name: AgentDispatcher

## Open questions

- Desktop shell: reuse AgentDesk's Electron shell or Tauri for a smaller install?
- Ledger in the same Postgres as LiteLLM or a separate schema/DB?
- Which AgentData validation result becomes the default A/B quality score?
- Public repo name and domain (agentdispatcher.dev?)
- Does the AgentDesk UI use exactly the same palette as AgentData? Mockups use the shared palette from the AgentData UI (AgentDesk source was not in the connected folder)

---
_Born as a design-mode export; review and refine — this file is the project's overview._

## Key Decisions

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

## Open Items

_No open items._

# agentdispatcher
_Last updated: 2026-10-26_

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

- Core architecture: LiteLLM proxy + OTel collector + Postgres ledger + React web UI + Electron desktop client
- Open-source licensing: Apache 2.0 for core, with THIRD_PARTY_NOTICES.md and CI license checks (blocking AGPL, commercial)
- Usage tracking: normalised usage_event ledger capturing timestamp, user, key, team, project, work_item, client, provider, model, with pricing attached
- AgentDesk integration: session→project/work-item attribution via OTEL_RESOURCE_ATTRIBUTES (agentdesk.project, agentdesk.work_item)
- AgentData integration: read-only semantic model (llm_usage.yaml) consumed by AgentData for cross-tenant analytics
- Model governance: allow-lists per virtual key/team/app, force-model rules, weighted routing by task tag or priority
- UI monitoring dimensions: breakdown by client, provider, model, source, with Overview KPIs and per-session drill-down
- Multi-tenant support: isolated usage ledgers per tenant with team-level key management and budget policies
- Mobile-first monitoring: React web app usable on desktop and mobile, shared design tokens with AgentDesk
- Agent instrumentation: small agents (e.g., AgentTrade) can integrate via OTEL_RESOURCE_ATTRIBUTES to tag scheduled/hard-to-monitor LLM jobs
- A/B experiments: routing policies support weighted model variants for experimentation
- Deployment: single docker-compose stack with LiteLLM, OTel collector, Postgres, Dispatcher core, and optional UI components
- Security hardening: pip-licenses/license-checker CI step, OTEL attribute validation, read-only AgentData role
- First-run UX: guided setup flow for docker-compose deployment, connection verification, and license attestation
- Extensibility: OTEL semantic conventions allow future sources (tools, frameworks) to emit usage without SDK changes

## Open Items

_No open items._

## Recent Work

- [ui] Clarifying monitoring scope: how to instrument scheduled/hard-to-monitor LLM jobs (e.g., AgentTrade) via OTEL attributes and small agent SDK
- [use_case] AgentDispatcher product definition: multi-tenant LLM usage ledger + monitoring UI + governance policies, integrating AgentDesk sessions and AgentData analytics
- [arch] Confirm agent instrumentation pattern: OTEL_RESOURCE_ATTRIBUTES for job/task tagging in user applications vs. in-app SDK wrapper
- [feature] Open-source attribution, security and privacy: THIRD_PARTY_NOTICES.md, README 'Built on' section, in-app licenses screen, CI license checks
- [feature] AgentDesk & AgentData integration: session attribution via OTEL_RESOURCE_ATTRIBUTES and semantic llm_usage model
- [feature] Install & first-run setup: docker-compose stack scaffold with guided connection verification and license flow

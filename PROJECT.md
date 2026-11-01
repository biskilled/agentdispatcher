# agentdispatcher
_Last updated: 2026-10-29_

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

- Core architecture: LiteLLM proxy + OTel collector + Postgres ledger + React web UI (browser-first, no Electron desktop required)
- Open-source licensing: Apache 2.0 for core, with THIRD_PARTY_NOTICES.md and CI license checks (blocking AGPL, commercial)
- Usage tracking: normalised usage_event ledger capturing timestamp, user, key, team, project, work_item, client, provider, model, with pricing attached
- AgentDesk integration: session→project/work-item attribution via OTEL_RESOURCE_ATTRIBUTES (agentdesk.project, agentdesk.work_item)
- AgentData integration: read-only semantic model (llm_usage.yaml) consumed by AgentData for cross-tenant analytics
- Model governance: allow-lists per virtual key/team/app, force-model rules, weighted routing by task tag or priority
- UI monitoring dimensions: breakdown by client, provider, model, source, with Overview KPIs and per-session drill-down
- Multi-tenant support: isolated usage ledgers per tenant with team-level key management and budget policies
- Mobile-first monitoring: React web app usable on desktop and mobile, shared design tokens with AgentDesk
- Agent instrumentation: small agents (e.g., AgentTrade) integrate via OTEL_RESOURCE_ATTRIBUTES to tag scheduled/hard-to-monitor LLM jobs
- A/B experiments: routing policies support weighted model variants for experimentation
- Deployment: single docker-compose stack with LiteLLM, OTel collector, Postgres, Dispatcher core, and optional UI components
- Security hardening: pip-licenses/license-checker CI step, OTEL attribute validation, read-only AgentData role
- First-run UX: guided setup flow for docker-compose deployment, connection verification, and license attestation
- Extensibility: OTEL semantic conventions allow future sources (tools, frameworks) to emit usage without SDK changes

## Open Items

_No open items._

## Recent Work

- [ui] Browser-first React monitoring: clarify why Electron desktop is not needed; confirm web UI handles desktop/mobile use cases
- [arch] Agent instrumentation pattern: finalize OTEL_RESOURCE_ATTRIBUTES for scheduled jobs (AgentTrade) vs. in-app SDK wrapper
- [feature] PostgreSQL tenant isolation: ensure all durable data (tenants, apps, usage events, policies) stored per-tenant
- [feature] Code practices: implement reusable classes, methods, and clear comments for maintainability across services
- [feature] AgentDesk & AgentData integration: validate session attribution and semantic llm_usage model consumption
- [feature] Install & first-run setup: docker-compose scaffold with guided connection verification and license flow

## Project Facts

### Architecture
- **cost_provenance_and_no_double_counting**: Maintain one tenant-scoped ledger with stable source/event/request IDs and parent-child execution links. SDK, OTel and gateway records for the same attempt are correlated, not counted as extra charges
- **yaml_configuration_optimisation**: Manage authorised application YAML using reusable repository, app API and local connector adapters. Preserve YAML as authoritative app configuration, record redacted versions/diffs/audits in tenant-sc
- **react_monitoring_and_embedded_sdk**: React is primarily the responsive desktop/mobile monitoring interface, not the app-execution agent. Use a small reusable OpenTelemetry-based integration inside consuming apps at their shared LLM clien
- **independent_services_single_monorepo**: Use one Git monorepo with real independently deployable services: responsive React/TypeScript UI, Python/FastAPI Dispatcher API, dedicated background worker/scheduler, LiteLLM gateway and OTel collect
- **postgresql_tenant_data**: PostgreSQL is the authoritative store for all durable AgentDispatcher product data: tenant/app identities, usage/price records, jobs/runs/traces, policies, configuration snapshots, evaluations and aud

### Convention
- **open_source_easy_install_and_credits**: AgentDispatcher is intended for public Apache-2.0 open-source distribution. Keep dependencies and custom code minimal; reuse suitable open-source components while preserving attribution and license ob
- **reusable_minimal_code**: Write once, reuse many: keep AgentDispatcher minimal with single-purpose classes, short well-named methods/functions and shared modules as the single source of each behaviour. Prefer composition and c

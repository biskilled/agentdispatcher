# agentdispatcher
_Last updated: 2026-11-01_

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
- API monitoring: general-purpose SDK for tracking any API usage (LLM, CoinGecko, Yahoo Finance, paid/free) with tenant-scoped catalog and pricing configuration
- Authentication: AgentDesk token (identity/session/membership), Google OAuth, user email, SDK dedicated hash keys per tenant
- A/B experiments: routing policies support weighted model variants for experimentation
- Deployment: single docker-compose stack with LiteLLM, OTel collector, Postgres, Dispatcher core, and optional UI components
- Security hardening: pip-licenses/license-checker CI step, OTEL attribute validation, read-only AgentData role, least-privilege tenant isolation

## Open Items

- `US10000` **AgentDispatcher — open-source LLM gateway and API usage monitoring** (use_case · in-progress)
- `FE10004` **Open-source quality, attribution, security and privacy** (feature · open)
- `FE10003` **AgentDesk, AgentData and application SDK integration** (feature · open)
- `FE10002` **Control & improvement: YAML configuration, policies and experiments** (feature · open)
- `FE10001` **Monitoring: overview, jobs, sessions, users and budgets** (feature · open)
- `FE10000` **Install & first-run setup** (feature · open)
- `TA10002` **Shared API quota and pricing engine with mixed-workload fixtures** (task · in-progress)
- `TA10001` **Admin API catalog and versioned provider plans** (task · in-progress)
- `TA10000` **Background job health, coverage and billing reconciliation** (task · in-progress)
- `TA10009` **YAML configuration connectors, version tracking and reversible updates** (task · open)
- `TA10008` **MCP gateway and external CLI monitoring adapters** (task · open)
- `TA10012` **Reusable LLM/API monitoring SDK and AgentTrade integration** (task · in-progress)
- `TA10007` **License checks, privacy and minimal-release verification** (task · in-progress)
- `TA10006` **Evidence-backed model policies and first A/B experiment** (task · open)
- `TA10003` **Google/email authentication, tenant SDK keys and AgentDesk attribution** (task · in-progress)
- `TA10005` **Tenant-scoped AgentData connector and usage semantic model** (task · open)
- `TA10010` **Responsive React monitoring UI: overview, jobs, sessions and connections** (task · in-progress)
- `TA10011` **Tenant-isolated PostgreSQL ledger, execution context and pricing** (task · in-progress)
- `TA10004` **Scaffold minimal monorepo and independently deployable Compose services** (task · in-progress)

## Recent Work

- [feature] Responsive React monitoring UI: overview, jobs, sessions and connections (in-progress)
- [feature] Tenant-isolated PostgreSQL ledger, execution context and pricing (in-progress)
- [feature] Google/email authentication, tenant SDK keys and AgentDesk attribution (in-progress)
- [feature] Shared API quota and pricing engine with mixed-workload fixtures (in-progress)
- [feature] Admin API catalog and versioned provider plans (in-progress)
- [feature] Reusable LLM/API monitoring SDK and AgentTrade integration (in-progress)

## Project Facts

### Architecture
- **cost_provenance_and_no_double_counting**: Maintain one tenant-scoped ledger with stable source/event/request IDs and parent-child execution links. SDK, OTel and gateway records for the same attempt are correlated, not counted as extra charges
- **yaml_configuration_optimisation**: Manage authorised application YAML using reusable repository, app API and local connector adapters. Preserve YAML as authoritative app configuration, record redacted versions/diffs/audits in tenant-sc
- **react_monitoring_and_embedded_sdk**: React is primarily the responsive desktop/mobile monitoring interface, not the app-execution agent. Use a small reusable OpenTelemetry-based integration inside consuming apps at their shared LLM clien
- **independent_services_single_monorepo**: Use one Git monorepo with real independently deployable services: responsive React/TypeScript UI, Python/FastAPI Dispatcher API, dedicated background worker/scheduler, LiteLLM gateway and OTel collect
- **postgresql_tenant_data**: PostgreSQL is the authoritative store for all durable AgentDispatcher product data: tenant/app identities, usage/price records, jobs/runs/traces, policies, configuration snapshots, evaluations and aud

### Constraint
- **deployment_model**: Independently deployable services (React, backend, SDK, MCP gateway) in single Git repository for open-source promotion

### Convention
- **open_source_easy_install_and_credits**: AgentDispatcher is intended for public Apache-2.0 open-source distribution. Keep dependencies and custom code minimal; reuse suitable open-source components while preserving attribution and license ob
- **reusable_minimal_code**: Write once, reuse many: keep AgentDispatcher minimal with single-purpose classes, short well-named methods/functions and shared modules as the single source of each behaviour. Prefer composition and c
- **auth_strategy**: React app: Google OAuth + email sign-in; SDK: hashed API keys scoped per tenant

### General
- **implementation_status**: 2026-11-01: initial Python/FastAPI API, PostgreSQL forced-RLS ledger/separate auth role, email sessions/Google OIDC routes, scoped hashed SDK keys, basic versioned API pricing, independent worker, Pyt
- **authentication_and_sdk_keys**: Authentication clarification (2026-11-01): Human access supports Google sign-in and verified email sign-in; passwordless email links are the initial design assumption. Resolve users, tenant membership
- **general_api_monitoring**: General API monitoring extension (2026-11-01): Monitor free and paid non-LLM APIs through the same reusable SDK and tenant-isolated PostgreSQL ledger, including market-data requests in scheduled jobs

### Stack
- **project_stack_email**: SMTP via Python smtplib
- **project_stack_scheduler**: Dedicated Python / FastAPI service
- **project_stack_backend**: Python / FastAPI
- **storage**: PostgreSQL per tenant for all durable data (usage ledger, API configs, quotas, user permissions)
- **ui_framework**: React web app, responsive for desktop and mobile, with admin interface for API/quota/pricing configuration
- **primary_gateway**: LiteLLM routes all LLM requests, tracks usage/costs, manages virtual keys and MCP gateway functionality

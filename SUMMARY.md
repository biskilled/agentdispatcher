# agentdispatcher — Summary

## Recent Work
- [feature] Responsive React monitoring UI: overview, jobs, sessions and connections (in-progress)
- [feature] Tenant-isolated PostgreSQL ledger, execution context and pricing (in-progress)
- [feature] Google/email authentication, tenant SDK keys and AgentDesk attribution (in-progress)
- [feature] Shared API quota and pricing engine with mixed-workload fixtures (in-progress)
- [feature] Admin API catalog and versioned provider plans (in-progress)
- [feature] Reusable LLM/API monitoring SDK and AgentTrade integration (in-progress)

## Stack & Architecture

- **gateway**: LiteLLM proxy
- **observability**: OpenTelemetry collector
- **database**: PostgreSQL
- **backend_runtime**: Python with FastAPI
- **ui_framework**: React + TypeScript + Vite
- **auth_integration**: AgentDesk token, Google OAuth, email, SDK hash keys per tenant
- **deployment**: Docker Compose
- **license**: Apache 2.0
- **key_management**: Virtual keys per team/app with LiteLLM settings
- **semantic_layer**: AgentData read-only connector (agentdata_ro role, llm_usage.yaml)
- **monitoring_sources**: OTEL_RESOURCE_ATTRIBUTES for project/work-item/job attribution
- **api_spec**: usage_event schema (ts, user, key, team, project, work_item, client, provider, model, api_id, quota, cost)
- **ci_checks**: pip-licenses/license-checker blocking AGPL and commercial dependencies
- **monorepo_services**: UI (React/Vite), API (FastAPI), background worker, independent deployable containers
- **api_catalog**: Tenant-scoped API registry with plans, quotas, pricing and alert thresholds

## Key Architectural Decisions

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

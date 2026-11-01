# agentdispatcher — Summary

## Recent Work
- [ui] Browser-first React monitoring: clarify why Electron desktop is not needed; confirm web UI handles desktop/mobile use cases
- [arch] Agent instrumentation pattern: finalize OTEL_RESOURCE_ATTRIBUTES for scheduled jobs (AgentTrade) vs. in-app SDK wrapper
- [feature] PostgreSQL tenant isolation: ensure all durable data (tenants, apps, usage events, policies) stored per-tenant
- [feature] Code practices: implement reusable classes, methods, and clear comments for maintainability across services
- [feature] AgentDesk & AgentData integration: validate session attribution and semantic llm_usage model consumption
- [feature] Install & first-run setup: docker-compose scaffold with guided connection verification and license flow

## Stack & Architecture

- **gateway**: LiteLLM proxy
- **observability**: OpenTelemetry collector
- **database**: PostgreSQL
- **backend_runtime**: Python with FastAPI
- **ui_framework**: React + TypeScript + Vite
- **auth_integration**: AgentDesk token (identity/session/membership)
- **deployment**: Docker Compose
- **license**: Apache 2.0
- **key_management**: Virtual keys per team/app with LiteLLM settings
- **semantic_layer**: AgentData read-only connector (agentdata_ro role, llm_usage.yaml)
- **monitoring_sources**: OTEL_RESOURCE_ATTRIBUTES for project/work-item/job attribution
- **api_spec**: usage_event schema (ts, user, key, team, project, work_item, client, provider, model)
- **ci_checks**: pip-licenses/license-checker blocking AGPL and commercial dependencies
- **monorepo_services**: UI (React/Vite), API (FastAPI), background worker, independent deployable containers

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
- A/B experiments: routing policies support weighted model variants for experimentation
- Deployment: single docker-compose stack with LiteLLM, OTel collector, Postgres, Dispatcher core, and optional UI components
- Security hardening: pip-licenses/license-checker CI step, OTEL attribute validation, read-only AgentData role
- First-run UX: guided setup flow for docker-compose deployment, connection verification, and license attestation
- Extensibility: OTEL semantic conventions allow future sources (tools, frameworks) to emit usage without SDK changes

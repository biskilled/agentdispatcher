# agentdispatcher — Summary

## Recent Work
- [ui] Default provider/model fallback and gateway configuration: users can add/rename service names and configure default provider/model routes through Sources → LLM gateway → Services & default; apps identified by separate gateway keys
- [ui] User confusion on connection options and MCP servers: clarification needed on why multiple connection options exist when LiteLLM gateway is primary; MCP server integration and CLI adapter usage patterns need documentation
- [gateway] LiteLLM gateway service deployed on Railway with tenant-scoped app key management
- [infrastructure] PostgreSQL 17.11 + pgvector 0.8.7 deployed on Railway with tenant isolation verified
- [bug] Live authentication not fully operational: Google OAuth and SMTP configuration require deployment; AgentDesk identity endpoint integration pending
- [bug] Upstream security vulnerabilities in LiteLLM and collector: two unresolved dependency findings remain in LiteLLM and upstream collector packages

## Stack & Architecture

- **gateway**: LiteLLM proxy (default LLM gateway)
- **observability**: OpenTelemetry collector
- **database**: PostgreSQL 17.11 with pgvector 0.8.7
- **backend_runtime**: Python 3.12 with FastAPI
- **ui_framework**: React + TypeScript + Vite
- **auth_integration**: AgentDesk token, Google OAuth, user email, SDK hash keys per tenant
- **deployment**: Docker Compose with 6 services + PostgreSQL
- **deployment_platform**: Railway
- **license**: Apache 2.0
- **key_management**: Virtual keys per team/app with LiteLLM settings
- **semantic_layer**: AgentData read-only connector (agentdata_ro role, llm_usage.yaml)
- **monitoring_sources**: OTEL_RESOURCE_ATTRIBUTES for project/work-item/job attribution; CLI adapters (Codex, Claude Code)
- **api_spec**: usage_event schema (ts, user, key, team, project, work_item, client, provider, model, api_id, quota, cost)
- **ci_checks**: pip-licenses/license-checker blocking AGPL and commercial dependencies
- **email**: SMTP via Python smtplib

## Key Architectural Decisions

- Core architecture: LiteLLM proxy as default gateway + OTel collector + PostgreSQL ledger + React web UI (browser-first, no Electron desktop required)
- Open-source licensing: Apache 2.0 for core, with THIRD_PARTY_NOTICES.md and CI license checks (blocking AGPL, commercial)
- Usage tracking: normalised usage_event ledger capturing timestamp, user, key, team, project, work_item, client, provider, model, with pricing attached
- AgentDesk integration: session→project/work-item attribution via OTEL_RESOURCE_ATTRIBUTES (agentdesk.project, agentdesk.work_item)
- AgentData integration: read-only semantic model (llm_usage.yaml) consumed by AgentData for cross-tenant analytics
- Model governance: allow-lists per virtual key/team/app, force-model rules, default provider/model fallback, weighted routing by task tag or priority
- UI monitoring dimensions: breakdown by client, provider, model, source, with Overview KPIs (by application, CLI/source, person) and per-session drill-down
- Multi-tenant support: isolated usage ledgers per tenant with team-level key management and budget policies
- Mobile-first monitoring: React web app usable on desktop and mobile, shared design tokens with AgentDesk
- Authentication: AgentDesk token (identity/session/membership), Google OAuth, user email, SDK dedicated hash keys per tenant; credentials via environment variables
- Deployment: six independently deployable services (UI, API, background worker, scheduler, LiteLLM proxy, OTel collector) in single docker-compose stack with PostgreSQL 17.11+pgvector
- Security hardening: pip-licenses/license-checker CI step, OTEL attribute validation, read-only AgentData role, least-privilege tenant isolation
- Agent instrumentation: small agents integrate via OTEL_RESOURCE_ATTRIBUTES to tag scheduled/hard-to-monitor LLM jobs
- API monitoring: general-purpose SDK for tracking any API usage (LLM, CoinGecko, Yahoo Finance, paid/free) with tenant-scoped catalog and pricing configuration
- A/B experiments: routing policies support weighted model variants for experimentation

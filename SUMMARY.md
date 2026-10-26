# agentdispatcher — Summary

## Recent Work
- [ui] Clarifying monitoring scope: how to instrument scheduled/hard-to-monitor LLM jobs (e.g., AgentTrade) via OTEL attributes and small agent SDK
- [use_case] AgentDispatcher product definition: multi-tenant LLM usage ledger + monitoring UI + governance policies, integrating AgentDesk sessions and AgentData analytics
- [arch] Confirm agent instrumentation pattern: OTEL_RESOURCE_ATTRIBUTES for job/task tagging in user applications vs. in-app SDK wrapper
- [feature] Open-source attribution, security and privacy: THIRD_PARTY_NOTICES.md, README 'Built on' section, in-app licenses screen, CI license checks
- [feature] AgentDesk & AgentData integration: session attribution via OTEL_RESOURCE_ATTRIBUTES and semantic llm_usage model
- [feature] Install & first-run setup: docker-compose stack scaffold with guided connection verification and license flow

## Stack & Architecture

- **gateway**: LiteLLM proxy
- **observability**: OpenTelemetry collector
- **database**: PostgreSQL
- **backend_runtime**: Python
- **ui_framework**: React + Vite
- **desktop_shell**: Electron
- **auth_integration**: AgentDesk token palette (light/dark themes)
- **deployment**: Docker Compose
- **license**: Apache 2.0
- **key_management**: Virtual keys per team/app with LiteLLM settings
- **semantic_layer**: AgentData read-only connector (agentdata_ro role)
- **monitoring_sources**: OTEL_RESOURCE_ATTRIBUTES for project/work-item attribution
- **api_spec**: usage_event schema (ts, user, key, team, project, work_item, client, provider, model)

## Key Architectural Decisions

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

# agentdispatcher — Summary

Self-installable, open-source (Apache 2.0) LLM gateway + usage ledger. Captures every LLM request and tool call across Claude Code, Codex, web chat and own apps (AgentData, AgentDesk) via two collectors — LiteLLM proxy for traffic we can route (metered) and an OpenTelemetry collector for CLI subscri

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

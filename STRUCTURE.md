<!-- Last updated: 2026-11-01 11:00 UTC -->
# Code Map: agentdispatcher
_Comprehensive code structure — single source for all LLMs. Refresh: `/memory`_

## Project Structure

```
app/
├── agents/
│   ├── mcp/
│   ├── providers/
│   ├── tools/
│   ├── yaml_config/
│   ├── __init__.py
│   └── agent.py
├── caller/
│   ├── __init__.py
│   ├── caller_client.py
│   ├── caller_index.py
│   └── caller_read.py
├── config/
│   └── pricing.yaml
├── core/
│   ├── __init__.py
│   ├── auth.py
│   ├── billing.py
│   ├── capture_canary.py
│   ├── ci_runner.py
│   ├── config.py
│   ├── context_assembler.py
│   ├── database.py
│   ├── db_log_handler.py
│   ├── db_migrations.py
│   ├── db_schema.sql
│   ├── design_export_settings.py
│   ├── doc_ai_settings.py
│   ├── execution_scope.py
│   ├── github_api.py
│   ├── invite.py
│   ├── logger.py
│   ├── messaging.py
│   ├── notify.py
│   ├── pipeline_log.py
│   ├── project_paths.py
│   ├── project_secrets.py
│   ├── prompt_loader.py
│   ├── railway_runtime.py
│   ├── ratelimit.py
│   ├── retention_settings.py
│   ├── scheduler.py
│   ├── secret_crypto.py
│   ├── server_repo.py
│   ├── skill_access.py
│   ├── skill_config.py
│   ├── skill_connectors.py
│   ├── skill_discovery.py
│   ├── skill_executor.py
│   ├── skill_loader.py
│   ├── skill_pack_loader.py
│   ├── skill_scope.py
│   ├── tags.py
│   ├── tenant_memory.py
│   ├── tenant_secrets.py
│   └── worktree_manager.py
├── data/
│   ├── __init__.py
│   ├── clean_pg_db.py
│   ├── dl_api_keys.py
│   ├── dl_seq.py
│   └── dl_user.py
├── memory/
│   ├── yaml_config/
│   ├── __init__.py
│   ├── _wi_classify.py
│   ├── _wi_helpers.py
│   ├── _wi_markdown.py
│   ├── _wi_skills.py
│   ├── alignment.py
│   ├── design_ingest.py
│   ├── entity_graph.py
│   ├── fact_consolidation.py
│   ├── hybrid_retrieval.py
│   ├── memory_code_complexity.py
│   ├── memory_code_parser.py
│   ├── memory_files.py
│   ├── memory_mirroring.py
│   ├── memory_sessions.py
│   ├── memory_work_items.py
│   ├── okf_export.py
│   ├── project_cleanup.py
│   ├── scoped_facts.py
│   └── wi_consolidation.py
├── qbr/
│   ├── ui/
│   ├── __init__.py
│   ├── qbr_data.py
│   ├── qbr_export.py
│   ├── qbr_overview.py
│   ├── qbr_periods.py
│   └── qbr_templates.py
├── routers/
│   ├── __init__.py
│   ├── route_admin.py
│   ├── route_agent_roles.py
│   ├── route_agents.py
│   ├── route_auth.py
│   ├── route_billing.py
│   ├── route_caller.py
│   ├── route_chat.py
│   ├── route_cli.py
│   ├── route_config_sync.py
│   ├── route_connectors.py
│   ├── route_deploy.py
│   ├── route_design.py
│   ├── route_documents.py
│   ├── route_files.py
│   ├── route_git.py
│   ├── route_history.py
│   ├── route_items.py
│   ├── route_logs.py
│   ├── route_memory.py
│   ├── route_messaging.py
│   ├── route_oauth.py
│   ├── route_projects.py
│   ├── route_prompts.py
│   ├── route_qbr.py
│   ├── route_runners.py
│   ├── route_schedules.py
│   ├── route_scoped_facts.py
│   ├── route_search.py
│   ├── route_skill_discovery.py
│   ├── route_system.py
│   ├── route_system_roles.py
│   ├── route_templates.py
│   ├── route_usage.py
│   ├── route_user_api_keys.py
│   └── route_work_items.py
├── scripts/
│   ├── labels/
│   ├── benchmark_retrieval.py
│   └── sync_file_skills.py
├── templates/
│   ├── codex_plugin/
│   ├── documents/
│   ├── file_skills/
│   ├── init_project/
│   ├── memory/
│   ├── mcp_catalog.yaml
│   ├── service_catalog.yaml
│   └── system_prompts.yaml
├── tests/
│   ├── __init__.py
│   ├── test_alignment_audit.py
│   ├── test_billing_budget.py
│   ├── test_caller_integration.py
│   ├── test_capture_canary.py
│   ├── test_chat_project_context.py
│   ├── test_classify_lifecycle.py
│   ├── test_classify_prompt_cache.py
│   ├── test_commit_parsing.py
│   ├── test_context_assembler.py
│   ├── test_contract_postgres.py
│   ├── test_cost_observability.py
│   ├── test_design_export.py
│   ├── test_design_export_flow.py
│   ├── test_document_multi_use_case.py
│   ├── test_draft_skill.py
│   ├── test_execution_scope.py
│   ├── test_fact_consolidation.py
│   ├── test_fact_supersede_mcp.py
│   ├── test_git_helpers.py
│   ├── test_git_provider_helpers.py
│   ├── test_hook_auto_commit.py
│   ├── test_hook_configuration.py
│   ├── test_hook_smoke_result.py
│   ├── test_hybrid_retrieval.py
│   ├── test_mcp_capture_alert.py
│   ├── test_mcp_project_scope.py
│   ├── test_mcp_roundtrip.py
│   ├── test_memory_cache_stability.py
│   ├── test_memory_files.py
│   ├── test_memory_graph_upgrades.py
│   ├── test_memory_visibility.py
│   ├── test_messaging.py
│   ├── test_oauth.py
│   ├── test_okf_export.py
│   ├── test_project_cache.py
│   ├── test_project_cleanup.py
│   ├── test_project_lifecycle.py
│   ├── test_qbr.py
│   ├── test_railway_runtime.py
│   ├── test_reconcile_project_state.py
│   ├── test_rescan.py
│   ├── test_retention_settings.py
│   ├── test_scheduler.py
│   ├── test_scheduler_service.py
│   ├── test_scheduler_weekday_migration.py
│   ├── test_schema_ddl_split.py
│   ├── test_scoped_facts.py
│   ├── test_secret_crypto.py
│   ├── test_skill_discovery.py
│   ├── test_skill_loader.py
│   ├── test_skill_projection_lossless.py
│   ├── test_skill_scope.py
│   ├── test_uc_md_folder.py
│   ├── test_usage_helpers.py
│   ├── test_usage_metering.py
│   ├── test_usefulness_feedback.py
│   ├── test_wi_markdown.py
│   ├── test_work_item_session_end.py
│   └── test_worktree_manager.py
├── __init__.py
├── AGENTS.md
├── CLAUDE.md
├── Dockerfile.scheduler
├── FACTS.md
├── GEMINI.md
├── global.md
├── main.py
├── mise.toml
├── OPEN_ITEMS.md
├── pwa_router.py
├── pyproject.toml
├── requirements.txt
├── scheduler_service.py
├── start_backend.sh
├── start_scheduler.sh
├── STRUCTURE.md
└── SUMMARY.md
```

## Active Work Items
_1 open use case(s), 18 open item(s) — grouped below._

### `US10000` AgentDispatcher — open-source LLM gateway and API usage monitoring _(18 open · 5 features, 13 tasks)_
- `TA10002` `task` Shared API quota and pricing engine with mixed-workload fixtures [in-progress]
- `TA10001` `task` Admin API catalog and versioned provider plans [in-progress]
- `TA10000` `task` Background job health, coverage and billing reconciliation [in-progress]
- _… +15 more_

---
_Generated by AgentDesk. Run `/memory` to refresh._
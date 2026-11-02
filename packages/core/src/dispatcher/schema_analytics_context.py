"""Append analytics dimensions without changing credential-bound view ownership."""

SQL_ANALYTICS_CONTEXT = """
CREATE OR REPLACE VIEW public.llm_usage WITH (security_invoker=true) AS
 SELECT tenant_id,event_id,attempt_id,service_id,occurred_at,app,environment,
 resource_kind,provider,model,api_id,job_run_id,status,cost,currency,cost_kind,
 verified_user_id,payload->>'user_id' AS reported_user_id,
 payload->>'operation_id' AS operation_id,payload->>'source' AS source,
 payload->>'operation' AS operation,payload->>'project' AS project,
 payload->>'work_item' AS work_item,payload->>'session_id' AS session_id,
 payload->>'trace_id' AS trace_id,payload->>'config_version' AS config_version,
 (payload->>'input_tokens')::bigint AS input_tokens,
 (payload->>'output_tokens')::bigint AS output_tokens,
 (payload->>'duration_ms')::numeric AS duration_ms,
 payload->>'feature' AS feature,payload->>'pipeline_role' AS pipeline_role,
 payload->>'experiment_id' AS experiment_id,payload->>'variant' AS variant,
 payload->>'usage_category' AS usage_category
 FROM public.mem_usage;
"""

"""Credential-bound analytics access; never trust a SQL caller's tenant filter."""

SQL_ANALYTICS = """
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='dispatcher_analytics') THEN
   CREATE ROLE dispatcher_analytics NOLOGIN NOSUPERUSER NOBYPASSRLS;
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS mng_analytics_roles (
 role_oid oid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES mng_tenants(id),
 enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE OR REPLACE FUNCTION public.dispatcher_analytics_tenant() RETURNS uuid
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
 SELECT binding.tenant_id FROM public.mng_analytics_roles binding
 JOIN pg_catalog.pg_roles role ON role.oid=binding.role_oid
 WHERE role.rolname=session_user AND binding.enabled
$$;
REVOKE ALL ON FUNCTION public.dispatcher_analytics_tenant() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.dispatcher_analytics_tenant() TO dispatcher_analytics;
GRANT USAGE ON SCHEMA public TO dispatcher_analytics;
ALTER POLICY tenant_scope ON mem_usage TO dispatcher_app;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
               AND tablename='mem_usage' AND policyname='analytics_scope') THEN
   CREATE POLICY analytics_scope ON mem_usage FOR SELECT TO dispatcher_analytics
     USING (tenant_id=public.dispatcher_analytics_tenant());
 END IF;
END $$;
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
 (payload->>'duration_ms')::numeric AS duration_ms
 FROM public.mem_usage;
GRANT SELECT ON public.mem_usage,public.llm_usage TO dispatcher_analytics;
"""

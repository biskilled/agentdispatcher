"""Tenant-isolated, immutable effective-time session context, migration 9."""

SQL_CONTEXT = """
CREATE TABLE IF NOT EXISTS mem_session_context (
 tenant_id uuid NOT NULL, id uuid NOT NULL, app text NOT NULL, environment text NOT NULL,
 session_id text NOT NULL, effective_at timestamptz NOT NULL, context jsonb NOT NULL,
 service_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,app,environment,session_id,effective_at)
);
ALTER TABLE mem_session_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_session_context FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
   AND tablename='mem_session_context' AND policyname='tenant_scope') THEN
   CREATE POLICY tenant_scope ON mem_session_context TO dispatcher_app
   USING (tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid)
   WITH CHECK (tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid);
 END IF;
END $$;
GRANT SELECT,INSERT ON mem_session_context TO dispatcher_app;
"""

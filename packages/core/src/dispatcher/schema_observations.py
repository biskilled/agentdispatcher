"""Non-billable correlated evidence alongside the immutable charge ledger, migration 13."""

SQL_OBSERVATIONS = """
CREATE TABLE IF NOT EXISTS mem_observations (
 tenant_id uuid NOT NULL,event_id uuid NOT NULL,service_id uuid NOT NULL,
 app text NOT NULL,environment text NOT NULL,expected_source text NOT NULL,
 correlation_kind text NOT NULL CHECK(correlation_kind IN ('attempt','operation')),
 attempt_id uuid NOT NULL,operation_id uuid NOT NULL,payload jsonb NOT NULL,
 evidence_hash text NOT NULL,verified_user_id uuid,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,event_id)
);
CREATE INDEX IF NOT EXISTS mem_usage_operation_source
 ON mem_usage(tenant_id,app,environment,(payload->>'operation_id'),(payload->>'source'));
ALTER TABLE mem_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_observations FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
   AND tablename='mem_observations' AND policyname='tenant_scope') THEN
   CREATE POLICY tenant_scope ON mem_observations TO dispatcher_app USING
     (tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid)
   WITH CHECK(tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid);
 END IF;
END $$;
GRANT SELECT,INSERT ON mem_observations TO dispatcher_app;
"""

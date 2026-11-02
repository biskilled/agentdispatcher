"""Append-only migration 15: attribution retention without altering billing evidence."""

SQL_RETENTION = """
CREATE TABLE IF NOT EXISTS mng_retention_policy (
 tenant_id uuid PRIMARY KEY REFERENCES mng_tenants(id),
 attribution_days integer CHECK(attribution_days IS NULL OR attribution_days > 0),
 revision integer NOT NULL, updated_by uuid NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE mng_retention_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE mng_retention_policy FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
   AND tablename='mng_retention_policy' AND policyname='tenant_scope') THEN
   CREATE POLICY tenant_scope ON mng_retention_policy
   USING(tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid)
   WITH CHECK(tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid);
 END IF;
END $$;
GRANT SELECT,INSERT,UPDATE ON mng_retention_policy TO dispatcher_app;
ALTER TABLE mem_usage ADD COLUMN IF NOT EXISTS attribution_expired_at timestamptz;
ALTER TABLE mem_observations ADD COLUMN IF NOT EXISTS attribution_expired_at timestamptz;
GRANT UPDATE(payload,verified_user_id,job_run_id,attribution_expired_at)
 ON mem_usage TO dispatcher_app;
GRANT UPDATE(payload,verified_user_id,attribution_expired_at) ON mem_observations TO dispatcher_app;
CREATE INDEX IF NOT EXISTS mem_usage_retention ON mem_usage(tenant_id,occurred_at)
 WHERE attribution_expired_at IS NULL;
CREATE INDEX IF NOT EXISTS mem_observations_retention ON mem_observations(tenant_id,created_at)
 WHERE attribution_expired_at IS NULL;
"""

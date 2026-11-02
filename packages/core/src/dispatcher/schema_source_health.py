"""Safe ingestion diagnostics, migration 14."""

SQL_SOURCE_HEALTH = """
CREATE TABLE IF NOT EXISTS mem_source_health (
 tenant_id uuid NOT NULL,service_id uuid NOT NULL,app text NOT NULL,environment text NOT NULL,
 source text NOT NULL,accepted_exports bigint NOT NULL DEFAULT 0,
 rejected_exports bigint NOT NULL DEFAULT 0,last_seen timestamptz NOT NULL DEFAULT now(),
 last_error text,PRIMARY KEY(tenant_id,service_id,source)
);
ALTER TABLE mem_source_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_source_health FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
   AND tablename='mem_source_health' AND policyname='tenant_scope') THEN
   CREATE POLICY tenant_scope ON mem_source_health TO dispatcher_app USING
     (tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid)
   WITH CHECK(tenant_id=nullif(current_setting('dispatcher.tenant_id',true),'')::uuid);
 END IF;
END $$;
GRANT SELECT,INSERT,UPDATE ON mem_source_health TO dispatcher_app;
"""

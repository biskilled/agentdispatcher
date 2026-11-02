"""Configuration observation and runtime evidence, migration 12."""

SQL_CONFIG_MONITORING = """
CREATE TABLE IF NOT EXISTS mem_config_heads (
 tenant_id uuid NOT NULL,source_id text NOT NULL,source_contract text NOT NULL,
 digest text,revision text,checked_at timestamptz NOT NULL,error_code text,
 PRIMARY KEY(tenant_id,source_id)
);
CREATE TABLE IF NOT EXISTS mem_config_runtime (
 tenant_id uuid NOT NULL,event_id uuid NOT NULL,source_id text NOT NULL,
 instance_id text NOT NULL,digest text NOT NULL,success boolean NOT NULL,
 occurred_at timestamptz NOT NULL,received_at timestamptz NOT NULL DEFAULT now(),
 service_id uuid NOT NULL,source_contract text NOT NULL,
 PRIMARY KEY(tenant_id,event_id)
);
CREATE INDEX IF NOT EXISTS mem_config_runtime_source
 ON mem_config_runtime(tenant_id,source_id,instance_id,occurred_at DESC);
ALTER TABLE mng_config_changes ADD COLUMN IF NOT EXISTS rollback_digest text;
ALTER TABLE mng_config_changes ADD COLUMN IF NOT EXISTS evaluation jsonb;
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['mem_config_heads','mem_config_runtime'] LOOP
   EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
   EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
   IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
      AND tablename=item AND policyname='tenant_scope') THEN
     EXECUTE format('CREATE POLICY tenant_scope ON %I TO dispatcher_app USING '
       '(tenant_id=nullif(current_setting(''dispatcher.tenant_id'',true),'''')::uuid) '
       'WITH CHECK (tenant_id=nullif(current_setting(''dispatcher.tenant_id'',true),'''')::uuid)',
       item);
   END IF;
   EXECUTE format('GRANT SELECT,INSERT ON %I TO dispatcher_app',item);
 END LOOP;
END $$;
GRANT UPDATE ON mem_config_heads TO dispatcher_app;
"""

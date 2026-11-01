"""Redacted configuration version and review history, migration 7."""

SQL_CONFIGURATION = """
CREATE TABLE IF NOT EXISTS mem_config_versions (
 tenant_id uuid NOT NULL,source_id text NOT NULL,digest text NOT NULL,revision text NOT NULL,
 inventory jsonb NOT NULL,app text NOT NULL,environment text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,source_id,digest)
);
CREATE TABLE IF NOT EXISTS mng_config_changes (
 tenant_id uuid NOT NULL,id uuid NOT NULL,source_id text NOT NULL,source_contract text NOT NULL,
 base_digest text NOT NULL,base_revision text NOT NULL,target_digest text NOT NULL,
 diff jsonb NOT NULL,state text NOT NULL DEFAULT 'proposed',result_revision text,
 created_by uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_config_actions (
 tenant_id uuid NOT NULL,change_id uuid NOT NULL,actor_id uuid NOT NULL,action text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(tenant_id,change_id) REFERENCES mng_config_changes(tenant_id,id)
);
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['mem_config_versions','mng_config_changes','mem_config_actions'] LOOP
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
GRANT UPDATE ON mng_config_changes TO dispatcher_app;
"""

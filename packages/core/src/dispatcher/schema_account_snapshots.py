"""Account snapshots and explicit test-data labels, migration 18."""

SQL_ACCOUNT_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS mng_usage_labels (
 tenant_id uuid NOT NULL,event_id uuid NOT NULL,is_test boolean NOT NULL,
 reason text NOT NULL,actor_id uuid NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,event_id),
 FOREIGN KEY(tenant_id,event_id) REFERENCES mem_usage(tenant_id,event_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mem_account_snapshots (
 tenant_id uuid NOT NULL,service_id uuid NOT NULL,provider text NOT NULL,account_key text NOT NULL,
 app text NOT NULL,environment text NOT NULL,verified_user_id uuid,
 observed_at timestamptz NOT NULL,snapshot jsonb NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,service_id,provider,account_key)
);
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['mng_usage_labels','mem_account_snapshots'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
  IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
    AND tablename=item AND policyname='tenant_scope') THEN
   EXECUTE format('CREATE POLICY tenant_scope ON %I TO dispatcher_app USING '
    '(tenant_id=nullif(current_setting(''dispatcher.tenant_id'',true),'''')::uuid) '
    'WITH CHECK (tenant_id=nullif(current_setting(''dispatcher.tenant_id'',true),'''')::uuid)',
    item);
  END IF;
 END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE ON mng_usage_labels,mem_account_snapshots TO dispatcher_app;
ALTER TABLE mng_sdk_keys DROP CONSTRAINT IF EXISTS mng_sdk_keys_source_type_check;
ALTER TABLE mng_sdk_keys ADD CONSTRAINT mng_sdk_keys_source_type_check
 CHECK(source_type IN ('sdk','codex','claude','mcp','codexbar'));
"""

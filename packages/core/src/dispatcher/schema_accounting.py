"""Append-only catalog, charge and quota evidence migration, version 3."""

SQL_ACCOUNTING = """
CREATE TABLE IF NOT EXISTS mng_connections (
 tenant_id uuid NOT NULL REFERENCES mng_tenants(id), id text NOT NULL,
 revision integer NOT NULL, config jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_config_audit (
 tenant_id uuid NOT NULL REFERENCES mng_tenants(id), id uuid NOT NULL,
 actor_id uuid NOT NULL, resource text NOT NULL, action text NOT NULL,
 before_value jsonb, after_value jsonb, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_usage_ratings (
 tenant_id uuid NOT NULL, event_id uuid NOT NULL, pool text NOT NULL,
 billing_start timestamptz, billing_end timestamptz, units numeric,
 plan_id uuid NOT NULL, occurred_at timestamptz NOT NULL,
 PRIMARY KEY(tenant_id,event_id),
 FOREIGN KEY(tenant_id,event_id) REFERENCES mem_usage(tenant_id,event_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id,plan_id) REFERENCES mng_api_plans(tenant_id,id)
);
CREATE INDEX IF NOT EXISTS mem_ratings_pool_time ON mem_usage_ratings(tenant_id,pool,occurred_at);
CREATE TABLE IF NOT EXISTS mem_period_charges (
 tenant_id uuid NOT NULL, pool text NOT NULL, period_start timestamptz NOT NULL,
 period_end timestamptz NOT NULL, plan_id uuid NOT NULL,
 amount numeric NOT NULL, currency text NOT NULL, kind text NOT NULL DEFAULT 'subscription',
 PRIMARY KEY(tenant_id,pool,period_start),
 FOREIGN KEY(tenant_id,plan_id) REFERENCES mng_api_plans(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_quota_events (
 tenant_id uuid NOT NULL, event_id uuid NOT NULL, pool text NOT NULL, rule_name text NOT NULL,
 units numeric, occurred_at timestamptz NOT NULL, plan_id uuid NOT NULL,
 PRIMARY KEY(tenant_id,event_id,rule_name),
 FOREIGN KEY(tenant_id,event_id) REFERENCES mem_usage(tenant_id,event_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id,plan_id) REFERENCES mng_api_plans(tenant_id,id)
);
CREATE INDEX IF NOT EXISTS mem_quota_pool_time
 ON mem_quota_events(tenant_id,pool,rule_name,occurred_at);
CREATE TABLE IF NOT EXISTS mem_alerts (
 tenant_id uuid NOT NULL, id uuid NOT NULL, dedup_key text NOT NULL,
 kind text NOT NULL, evidence jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,dedup_key)
);
CREATE TABLE IF NOT EXISTS mem_provider_snapshots (
 tenant_id uuid NOT NULL, id uuid NOT NULL, pool text NOT NULL, provider_ref text NOT NULL,
 period_start timestamptz NOT NULL, period_end timestamptz NOT NULL,
 amount numeric, currency text, units numeric, observed_at timestamptz NOT NULL,
 source_note text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,pool,provider_ref)
);
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['mng_connections','mem_config_audit','mem_usage_ratings',
 'mem_period_charges','mem_quota_events','mem_alerts','mem_provider_snapshots'] LOOP
   EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', item);
   EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', item);
   IF NOT EXISTS(SELECT FROM pg_policies WHERE schemaname='public'
      AND tablename=item AND policyname='tenant_scope') THEN
     EXECUTE format('CREATE POLICY tenant_scope ON %I USING '
       '(tenant_id = nullif(current_setting(''dispatcher.tenant_id'',true),'''')::uuid) '
       'WITH CHECK (tenant_id = '
       'nullif(current_setting(''dispatcher.tenant_id'',true),'''')::uuid)', item);
   END IF;
   EXECUTE format('GRANT SELECT,INSERT ON %I TO dispatcher_app', item);
 END LOOP;
END $$;
GRANT UPDATE ON mng_connections TO dispatcher_app;
"""

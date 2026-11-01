"""Durable monitoring schedules, leases and explicit cost adjustments, migration 4."""

SQL_OPERATIONS = """
CREATE TABLE IF NOT EXISTS mng_schedules (
 tenant_id uuid NOT NULL, id text NOT NULL, config jsonb NOT NULL,
 revision integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_expected_runs (
 tenant_id uuid NOT NULL, schedule_id text NOT NULL, scheduled_for timestamptz NOT NULL,
 checked_at timestamptz NOT NULL, PRIMARY KEY(tenant_id,schedule_id,scheduled_for),
 FOREIGN KEY(tenant_id,schedule_id) REFERENCES mng_schedules(tenant_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mng_worker_leases (
 tenant_id uuid NOT NULL, task text NOT NULL, owner uuid NOT NULL,
 lease_until timestamptz NOT NULL, completed_at timestamptz,
 PRIMARY KEY(tenant_id,task)
);
CREATE TABLE IF NOT EXISTS mng_budgets (
 tenant_id uuid NOT NULL, id text NOT NULL, config jsonb NOT NULL,
 revision integer NOT NULL DEFAULT 1, PRIMARY KEY(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_adjustments (
 tenant_id uuid NOT NULL, id uuid NOT NULL, event_id uuid NOT NULL, amount numeric NOT NULL,
 currency text NOT NULL, source_ref text NOT NULL, reason text NOT NULL,
 created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id), UNIQUE(tenant_id,source_ref),
 FOREIGN KEY(tenant_id,event_id) REFERENCES mem_usage(tenant_id,event_id)
);
ALTER TABLE mem_job_runs ADD COLUMN IF NOT EXISTS started_at timestamptz;
UPDATE mem_job_runs SET started_at=occurred_at WHERE started_at IS NULL;
ALTER TABLE mem_job_runs ADD COLUMN IF NOT EXISTS schedule_id text;
ALTER TABLE mem_job_runs ADD COLUMN IF NOT EXISTS scheduled_for timestamptz;
CREATE INDEX IF NOT EXISTS mem_jobs_schedule
 ON mem_job_runs(tenant_id,schedule_id,scheduled_for);
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['mng_schedules','mem_expected_runs','mng_worker_leases',
 'mng_budgets','mem_adjustments'] LOOP
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
GRANT UPDATE ON mng_schedules,mng_worker_leases,mng_budgets TO dispatcher_app;
"""

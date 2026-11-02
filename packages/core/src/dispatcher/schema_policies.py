"""Audited model policy revisions and immutable experiment evidence, migration 10."""

SQL_POLICIES = """
CREATE TABLE IF NOT EXISTS mng_model_policies (
 tenant_id uuid NOT NULL,id text NOT NULL,app text NOT NULL,environment text NOT NULL,
 revision integer NOT NULL,config jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,app,environment)
);
CREATE TABLE IF NOT EXISTS mem_policy_versions (
 tenant_id uuid NOT NULL,policy_id text NOT NULL,revision integer NOT NULL,config jsonb NOT NULL,
 actor_id uuid NOT NULL,action text NOT NULL,evidence jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,policy_id,revision)
);
CREATE TABLE IF NOT EXISTS mng_experiments (
 tenant_id uuid NOT NULL,id uuid NOT NULL,app text NOT NULL,environment text NOT NULL,
 config jsonb NOT NULL,created_by uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_assignments (
 tenant_id uuid NOT NULL,id uuid NOT NULL,experiment_id uuid NOT NULL,task_id uuid NOT NULL,
 variant text NOT NULL,model text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,id),UNIQUE(tenant_id,experiment_id,task_id),
 FOREIGN KEY(tenant_id,experiment_id) REFERENCES mng_experiments(tenant_id,id)
);
CREATE TABLE IF NOT EXISTS mem_task_outcomes (
 tenant_id uuid NOT NULL,assignment_id uuid NOT NULL,outcome jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(tenant_id,assignment_id),
 FOREIGN KEY(tenant_id,assignment_id) REFERENCES mem_assignments(tenant_id,id)
);
DO $$ DECLARE item text; BEGIN
 FOREACH item IN ARRAY ARRAY['mng_model_policies','mem_policy_versions','mng_experiments',
   'mem_assignments','mem_task_outcomes'] LOOP
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
GRANT UPDATE ON mng_model_policies TO dispatcher_app;
"""

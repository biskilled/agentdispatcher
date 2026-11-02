"""Single migration owner; append immutable migrations rather than changing deployed SQL."""

import os

import psycopg

from dispatcher.schema_access import SQL_ACCESS
from dispatcher.schema_accounting import SQL_ACCOUNTING
from dispatcher.schema_agentdesk import SQL_AGENTDESK
from dispatcher.schema_analytics import SQL_ANALYTICS
from dispatcher.schema_configuration import SQL_CONFIGURATION
from dispatcher.schema_context import SQL_CONTEXT
from dispatcher.schema_gateway import SQL_GATEWAY
from dispatcher.schema_operations import SQL_OPERATIONS
from dispatcher.schema_policies import SQL_POLICIES
from dispatcher.schema_tools import SQL_TOOLS

_SQL_LOCK = "SELECT pg_advisory_xact_lock(73190521)"
_SQL_TRACKING = """
CREATE TABLE IF NOT EXISTS mng_migrations (
    version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
)
"""
_SQL_APPLIED = "SELECT version FROM mng_migrations WHERE version = %s"
_SQL_RECORD = "INSERT INTO mng_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING"

_SQL_INITIAL = """
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dispatcher_app') THEN
    CREATE ROLE dispatcher_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dispatcher_auth') THEN
    CREATE ROLE dispatcher_auth NOLOGIN NOSUPERUSER NOBYPASSRLS;
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS mng_tenants (
    id uuid PRIMARY KEY, name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mng_users (
    id uuid PRIMARY KEY, email text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mng_identities (
    issuer text NOT NULL, subject text NOT NULL, user_id uuid NOT NULL REFERENCES mng_users(id),
    PRIMARY KEY (issuer, subject)
);
CREATE TABLE IF NOT EXISTS mng_memberships (
    tenant_id uuid NOT NULL REFERENCES mng_tenants(id),
    user_id uuid NOT NULL REFERENCES mng_users(id),
    role text NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
    PRIMARY KEY (tenant_id, user_id)
);
CREATE TABLE IF NOT EXISTS mng_sessions (
    token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES mng_users(id),
    expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mng_login_tokens (
    token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES mng_users(id),
    expires_at timestamptz NOT NULL, used_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mng_login_limits (
    identity_hash text PRIMARY KEY, window_start timestamptz NOT NULL, requests integer NOT NULL
);
CREATE TABLE IF NOT EXISTS mng_sdk_keys (
    id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES mng_tenants(id),
    token_hash text NOT NULL UNIQUE, name text NOT NULL, app text NOT NULL,
    environment text NOT NULL, created_by uuid NOT NULL REFERENCES mng_users(id),
    created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
    revoked_at timestamptz, last_used_at timestamptz
);
CREATE TABLE IF NOT EXISTS mng_auth_audit (
    id bigserial PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES mng_tenants(id),
    actor_id uuid NOT NULL, action text NOT NULL, target_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mng_api_plans (
    tenant_id uuid NOT NULL REFERENCES mng_tenants(id), id uuid NOT NULL,
    api_id text NOT NULL, effective_at timestamptz NOT NULL, plan jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, id), UNIQUE (tenant_id, api_id, effective_at)
);
CREATE TABLE IF NOT EXISTS mem_usage (
    tenant_id uuid NOT NULL REFERENCES mng_tenants(id), event_id uuid NOT NULL,
    service_id uuid NOT NULL REFERENCES mng_sdk_keys(id), attempt_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL, app text NOT NULL, environment text NOT NULL,
    resource_kind text NOT NULL, provider text NOT NULL, model text,
    api_id text, job_run_id uuid, status text NOT NULL, payload jsonb NOT NULL,
    evidence_hash text NOT NULL, cost numeric, currency text, cost_kind text NOT NULL,
    plan_id uuid, created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id),
    UNIQUE (tenant_id, app, environment, attempt_id),
    FOREIGN KEY (tenant_id, plan_id) REFERENCES mng_api_plans(tenant_id, id)
);
CREATE INDEX IF NOT EXISTS mem_usage_tenant_time ON mem_usage(tenant_id, occurred_at DESC);
CREATE TABLE IF NOT EXISTS mem_job_runs (
    tenant_id uuid NOT NULL REFERENCES mng_tenants(id), run_id uuid NOT NULL,
    service_id uuid NOT NULL REFERENCES mng_sdk_keys(id), app text NOT NULL,
    environment text NOT NULL, name text NOT NULL, state text NOT NULL,
    occurred_at timestamptz NOT NULL, trace_id text,
    received_at timestamptz NOT NULL DEFAULT now(), stale boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tenant_id, run_id)
);
CREATE TABLE IF NOT EXISTS mem_worker_health (
    tenant_id uuid PRIMARY KEY REFERENCES mng_tenants(id), last_seen timestamptz NOT NULL
);
ALTER TABLE mng_api_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE mng_api_plans FORCE ROW LEVEL SECURITY;
ALTER TABLE mem_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_usage FORCE ROW LEVEL SECURITY;
ALTER TABLE mem_job_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_job_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE mem_worker_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE mem_worker_health FORCE ROW LEVEL SECURITY;
DO $$ DECLARE item text; BEGIN
  FOREACH item IN ARRAY ARRAY['mng_api_plans','mem_usage','mem_job_runs','mem_worker_health'] LOOP
    IF NOT EXISTS (SELECT FROM pg_policies WHERE schemaname='public'
                   AND tablename=item AND policyname='tenant_scope') THEN
      EXECUTE format('CREATE POLICY tenant_scope ON %I USING '
        '(tenant_id = nullif(current_setting(''dispatcher.tenant_id'', true), '''')::uuid) '
        'WITH CHECK (tenant_id = '
        'nullif(current_setting(''dispatcher.tenant_id'', true), '''')::uuid)', item);
    END IF;
  END LOOP;
END $$;
GRANT USAGE ON SCHEMA public TO dispatcher_app, dispatcher_auth;
GRANT SELECT, INSERT ON mng_api_plans, mem_usage TO dispatcher_app;
GRANT SELECT, INSERT, UPDATE ON mem_job_runs, mem_worker_health TO dispatcher_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON mng_tenants, mng_users, mng_identities,
    mng_memberships, mng_sessions, mng_login_tokens, mng_login_limits, mng_sdk_keys
    TO dispatcher_auth;
GRANT SELECT, INSERT ON mng_auth_audit TO dispatcher_auth;
GRANT USAGE, SELECT ON SEQUENCE mng_auth_audit_id_seq TO dispatcher_auth;
GRANT SELECT ON mng_migrations TO dispatcher_auth;
"""

MIGRATIONS = (
    (1, _SQL_INITIAL),
    (2, SQL_ACCESS),
    (3, SQL_ACCOUNTING),
    (4, SQL_OPERATIONS),
    (5, SQL_GATEWAY),
    (6, SQL_ANALYTICS),
    (7, SQL_CONFIGURATION),
    (8, SQL_AGENTDESK),
    (9, SQL_CONTEXT),
    (10, SQL_POLICIES),
    (11, SQL_TOOLS),
)


def migrate(dsn: str) -> None:
    """Apply new migrations under a database lock using a deployment-only owner."""
    with psycopg.connect(dsn) as connection:
        connection.execute(_SQL_LOCK)
        connection.execute(_SQL_TRACKING)
        for version, statement in MIGRATIONS:
            if connection.execute(_SQL_APPLIED, (version,)).fetchone():
                continue
            connection.execute(statement)
            connection.execute(_SQL_RECORD, (version,))


def main() -> None:
    """Run the migration deployment job; never use its DSN in the API or worker."""
    migrate(os.environ["DISPATCHER_MIGRATION_DATABASE_URL"])


if __name__ == "__main__":
    main()

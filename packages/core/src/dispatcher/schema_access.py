"""Append-only access-control migration, version 2."""

# ruff: noqa: E501 -- keep applied SQL text immutable

SQL_ACCESS = """
CREATE TABLE IF NOT EXISTS mng_invitations (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES mng_tenants(id),
 email text NOT NULL, role text NOT NULL CHECK(role IN ('owner','admin','member','viewer')),
 token_hash text NOT NULL UNIQUE, created_by uuid NOT NULL REFERENCES mng_users(id),
 expires_at timestamptz NOT NULL, accepted_at timestamptz, revoked_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mng_view_grants (
 tenant_id uuid NOT NULL, user_id uuid NOT NULL, app text NOT NULL,
 PRIMARY KEY(tenant_id,user_id,app),
 FOREIGN KEY(tenant_id,user_id) REFERENCES mng_memberships(tenant_id,user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mng_delegations (
 token_hash text PRIMARY KEY, tenant_id uuid NOT NULL, user_id uuid NOT NULL,
 app text NOT NULL, session_hash text NOT NULL REFERENCES mng_sessions(token_hash) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL,
 FOREIGN KEY(tenant_id,user_id) REFERENCES mng_memberships(tenant_id,user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS mng_oidc_flows (
 state_hash text PRIMARY KEY, expires_at timestamptz NOT NULL, used_at timestamptz
);
ALTER TABLE mem_usage ADD COLUMN IF NOT EXISTS verified_user_id uuid REFERENCES mng_users(id);
CREATE INDEX IF NOT EXISTS mem_usage_actor ON mem_usage(tenant_id,verified_user_id);
GRANT SELECT,INSERT,UPDATE,DELETE ON mng_invitations,mng_view_grants,mng_delegations,
 mng_oidc_flows TO dispatcher_auth;
"""

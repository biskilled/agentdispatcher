"""Append-only AgentDesk identity bindings, migration 8."""

SQL_AGENTDESK = """
CREATE TABLE IF NOT EXISTS mng_agentdesk_bindings (
 tenant_id uuid PRIMARY KEY REFERENCES mng_tenants(id),
 issuer text NOT NULL, client_id text NOT NULL,
 created_by uuid NOT NULL REFERENCES mng_users(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(issuer,client_id)
);
CREATE TABLE IF NOT EXISTS mng_agentdesk_links (
 tenant_id uuid NOT NULL REFERENCES mng_agentdesk_bindings(tenant_id) ON DELETE CASCADE,
 user_id uuid NOT NULL, subject text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,user_id),
 UNIQUE(tenant_id,subject),
 FOREIGN KEY(tenant_id,user_id) REFERENCES mng_memberships(tenant_id,user_id) ON DELETE CASCADE
);
GRANT SELECT,INSERT,DELETE ON mng_agentdesk_bindings,mng_agentdesk_links TO dispatcher_auth;
"""

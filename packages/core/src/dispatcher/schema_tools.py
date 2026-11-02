"""Session-bound, hash-only delegated tool access, migration 11."""

SQL_TOOLS = """
CREATE TABLE IF NOT EXISTS mng_tool_tokens (
 id uuid PRIMARY KEY,token_hash text NOT NULL UNIQUE,tenant_id uuid NOT NULL,user_id uuid NOT NULL,
 session_hash text NOT NULL REFERENCES mng_sessions(token_hash) ON DELETE CASCADE,
 can_write_policy boolean NOT NULL DEFAULT false,resource text NOT NULL,
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(tenant_id,user_id) REFERENCES mng_memberships(tenant_id,user_id) ON DELETE CASCADE
);
GRANT SELECT,INSERT,DELETE ON mng_tool_tokens TO dispatcher_auth;
"""

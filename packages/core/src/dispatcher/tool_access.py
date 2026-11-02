"""Delegated MCP/API access retains the user's live session, membership and app restrictions."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException

from dispatcher.auth import member_principal, require_admin, verifier

_SQL_ADD = """
INSERT INTO mng_tool_tokens(id,token_hash,tenant_id,user_id,session_hash,
can_write_policy,resource,expires_at)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_AUTH = """
SELECT t.tenant_id,t.user_id,t.can_write_policy,t.resource,t.expires_at,m.role
FROM mng_tool_tokens t JOIN mng_sessions s ON s.token_hash=t.session_hash
JOIN mng_memberships m ON (m.tenant_id,m.user_id)=(t.tenant_id,t.user_id)
WHERE t.token_hash=%s AND t.tenant_id=%s AND t.expires_at>now() AND s.expires_at>now()
"""
_SQL_LIST = """
SELECT id,can_write_policy,expires_at,created_at FROM mng_tool_tokens
WHERE tenant_id=%s AND user_id=%s ORDER BY created_at DESC
"""
_SQL_REVOKE = "DELETE FROM mng_tool_tokens WHERE tenant_id=%s AND user_id=%s AND id=%s RETURNING id"
_SQL_AUDIT = """
INSERT INTO mng_auth_audit(tenant_id,actor_id,action,target_id) VALUES(%s,%s,%s,%s)
"""


class ToolAccess:
    """A tool credential cannot become an SDK key, browser session or another tenant's token."""

    def __init__(self, auth):
        self.auth, self.db = auth, auth.db

    def issue(self, session, tenant_id, can_write_policy):
        """Issue a short-lived grant, rechecking the human's current membership and permission."""
        principal = self.auth.human(session, tenant_id)
        if can_write_policy:
            self.auth.recent_user(session)
            require_admin(principal)
        secret = f"dta_{tenant_id}_" + self.auth.new_secret()
        token_id = uuid4()
        expires = datetime.now(UTC) + timedelta(seconds=self.db.settings.tool_token_seconds)
        with self.db.auth() as connection:
            connection.execute(
                _SQL_ADD,
                (
                    token_id,
                    verifier(secret),
                    tenant_id,
                    principal.subject_id,
                    verifier(session),
                    can_write_policy,
                    self.db.settings.tool_resource_url
                    or self.db.settings.public_url.rstrip("/") + "/api/tools",
                    expires,
                ),
            )
            connection.execute(
                _SQL_AUDIT, (tenant_id, principal.subject_id, "tools.issued", token_id)
            )
        return {
            "id": token_id,
            "secret": secret,
            "expires_at": expires,
            "can_write_policy": can_write_policy,
        }

    def principal(self, token, tenant_id, write=False):
        """Recheck session revocation and membership on each request."""
        with self.db.auth() as connection:
            row = connection.execute(_SQL_AUTH, (verifier(token), tenant_id)).fetchone()
            if not row:
                raise HTTPException(
                    401, "Tool access is expired, revoked or outside this workspace"
                )
            principal = member_principal(connection, tenant_id, row["user_id"], row["role"])
        if write:
            if not row["can_write_policy"]:
                raise HTTPException(403, "This tool credential is read-only")
            require_admin(principal)
        return principal, row

    def list(self, principal):
        """List only the caller's own delegated credentials without hashes or secrets."""
        with self.db.auth() as connection:
            return connection.execute(
                _SQL_LIST, (principal.tenant_id, principal.subject_id)
            ).fetchall()

    def revoke(self, principal, token_id):
        """Revoke one of this person's tool credentials immediately."""
        with self.db.auth() as connection:
            if not connection.execute(
                _SQL_REVOKE, (principal.tenant_id, principal.subject_id, token_id)
            ).fetchone():
                raise HTTPException(404, "Tool credential not found")
            connection.execute(
                _SQL_AUDIT, (principal.tenant_id, principal.subject_id, "tools.revoked", token_id)
            )

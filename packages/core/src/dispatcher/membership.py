"""Invitations and membership administration share one serialised owner invariant."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException

from dispatcher.auth import AuthService, require_admin, verifier
from dispatcher.contracts import Principal

_SQL_LOCK = "SELECT id FROM mng_tenants WHERE id=%s FOR UPDATE"
_SQL_MEMBERS = """
SELECT u.id,u.email,m.role,coalesce(array_agg(g.app) FILTER (WHERE g.app IS NOT NULL),'{}') apps
FROM mng_memberships m JOIN mng_users u ON u.id=m.user_id LEFT JOIN mng_view_grants g
ON (g.tenant_id,g.user_id)=(m.tenant_id,m.user_id) WHERE m.tenant_id=%s
GROUP BY u.id,u.email,m.role ORDER BY u.email
"""
_SQL_MEMBER = "SELECT role FROM mng_memberships WHERE tenant_id=%s AND user_id=%s"
_SQL_OWNERS = "SELECT count(*) n FROM mng_memberships WHERE tenant_id=%s AND role='owner'"
_SQL_ROLE = "UPDATE mng_memberships SET role=%s WHERE tenant_id=%s AND user_id=%s"
_SQL_REMOVE = "DELETE FROM mng_memberships WHERE tenant_id=%s AND user_id=%s"
_SQL_GRANTS_DELETE = "DELETE FROM mng_view_grants WHERE tenant_id=%s AND user_id=%s"
_SQL_GRANT = """
INSERT INTO mng_view_grants(tenant_id,user_id,app) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
"""
_SQL_INVITE = """
INSERT INTO mng_invitations(id,tenant_id,email,role,token_hash,created_by,expires_at)
VALUES (%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_INVITATIONS = """
SELECT id,email,role,expires_at,accepted_at,revoked_at FROM mng_invitations
WHERE tenant_id=%s ORDER BY created_at DESC
"""
_SQL_REVOKE = """
UPDATE mng_invitations SET revoked_at=now() WHERE tenant_id=%s AND id=%s RETURNING id
"""
_SQL_ACCEPT = """
UPDATE mng_invitations SET accepted_at=now() WHERE token_hash=%s AND email=%s
AND expires_at>now() AND revoked_at IS NULL AND accepted_at IS NULL
RETURNING tenant_id,role,created_by,id
"""
_SQL_INVITE_TENANT = "SELECT tenant_id FROM mng_invitations WHERE token_hash=%s"
_SQL_JOIN = """
INSERT INTO mng_memberships(tenant_id,user_id,role) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING
"""
_SQL_AUDIT = """
INSERT INTO mng_auth_audit(tenant_id,actor_id,action,target_id) VALUES(%s,%s,%s,%s)
"""
_SQL_IDENTITY = "SELECT user_id FROM mng_identities WHERE issuer='email' AND subject=%s"
_SQL_USER = "INSERT INTO mng_users(id,email) VALUES(%s,%s)"
_SQL_EMAIL = "INSERT INTO mng_identities(issuer,subject,user_id) VALUES('email',%s,%s)"
_SQL_EMAIL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_PROVED_EMAIL = """
SELECT subject FROM mng_identities WHERE user_id=%s AND issuer='email'
"""


def ensure_email_identity(connection, email: str) -> UUID:
    """Provision a login identity without granting membership or treating it as verified."""
    connection.execute(_SQL_EMAIL_LOCK, (email,))
    row = connection.execute(_SQL_IDENTITY, (email,)).fetchone()
    if row:
        return row["user_id"]
    user_id = uuid4()
    connection.execute(_SQL_USER, (user_id, email))
    connection.execute(_SQL_EMAIL, (email, user_id))
    return user_id


class MembershipService:
    """Manage tenant access; admins cannot create or change owners or other admins."""

    def __init__(self, auth: AuthService):
        self.auth, self.db = auth, auth.db

    def _authorise(self, principal, target_role, new_role):
        require_admin(principal)
        if principal.role != "owner" and (
            target_role in {"owner", "admin"} or new_role in {"owner", "admin"}
        ):
            raise HTTPException(403, "Owner access required for owner/admin changes")

    def _lock_actor(self, connection, principal):
        connection.execute(_SQL_LOCK, (principal.tenant_id,))
        actor = connection.execute(
            _SQL_MEMBER, (principal.tenant_id, principal.subject_id)
        ).fetchone()
        if not actor:
            raise HTTPException(403, "Tenant membership required")
        principal = principal.model_copy(update={"role": actor["role"]})
        require_admin(principal)
        return principal

    def members(self, principal: Principal) -> list:
        """List current roles and explicit app grants for this tenant only."""
        require_admin(principal)
        with self.db.auth() as connection:
            return connection.execute(_SQL_MEMBERS, (principal.tenant_id,)).fetchall()

    def update(self, principal: Principal, user_id: UUID, role: str | None, apps: list[str]):
        """Serialize membership changes so concurrent requests cannot remove the last owner."""
        require_admin(principal)
        with self.db.auth() as connection:
            principal = self._lock_actor(connection, principal)
            target = connection.execute(_SQL_MEMBER, (principal.tenant_id, user_id)).fetchone()
            if not target:
                raise HTTPException(404, "Member not found")
            self._authorise(principal, target["role"], role)
            if target["role"] == "owner" and role != "owner":
                if connection.execute(_SQL_OWNERS, (principal.tenant_id,)).fetchone()["n"] <= 1:
                    raise HTTPException(409, "A tenant must retain at least one owner")
            if role is None:
                connection.execute(_SQL_REMOVE, (principal.tenant_id, user_id))
            else:
                connection.execute(_SQL_ROLE, (role, principal.tenant_id, user_id))
                connection.execute(_SQL_GRANTS_DELETE, (principal.tenant_id, user_id))
                for app in set(apps):
                    connection.execute(_SQL_GRANT, (principal.tenant_id, user_id, app))
            connection.execute(
                _SQL_AUDIT,
                (
                    principal.tenant_id,
                    principal.subject_id,
                    "member.updated" if role else "member.removed",
                    user_id,
                ),
            )

    def invite(self, principal: Principal, email: str, role: str) -> dict:
        """Return a single-use invite for explicit sharing; login independently proves the email."""
        self._authorise(principal, None, role)
        token, invite_id = self.auth.new_secret(), uuid4()
        expiry = datetime.now(UTC) + timedelta(seconds=self.db.settings.invite_seconds)
        with self.db.auth() as connection:
            principal = self._lock_actor(connection, principal)
            self._authorise(principal, None, role)
            ensure_email_identity(connection, email)
            connection.execute(
                _SQL_INVITE,
                (
                    invite_id,
                    principal.tenant_id,
                    email,
                    role,
                    verifier(token),
                    principal.subject_id,
                    expiry,
                ),
            )
            connection.execute(
                _SQL_AUDIT, (principal.tenant_id, principal.subject_id, "invite.created", invite_id)
            )
        return {"id": invite_id, "token": token, "expires_at": expiry}

    def accept(self, user: dict, token: str) -> dict:
        """Accept only as the independently authenticated invited email identity."""
        with self.db.auth() as connection:
            identities = connection.execute(_SQL_PROVED_EMAIL, (user["user_id"],)).fetchall()
            emails = {row["subject"] for row in identities}
            if user["email"] not in emails:
                raise HTTPException(403, "Sign in with the invited email account first")
            pending = connection.execute(_SQL_INVITE_TENANT, (verifier(token),)).fetchone()
            if not pending:
                raise HTTPException(401, "Invalid invitation")
            connection.execute(_SQL_LOCK, (pending["tenant_id"],))
            invite = connection.execute(_SQL_ACCEPT, (verifier(token), user["email"])).fetchone()
            if not invite:
                raise HTTPException(401, "Invalid, expired or already used invitation")
            inviter = connection.execute(
                _SQL_MEMBER, (invite["tenant_id"], invite["created_by"])
            ).fetchone()
            if not inviter or inviter["role"] not in {"owner", "admin"}:
                raise HTTPException(403, "Invitation issuer no longer has permission")
            if invite["role"] in {"owner", "admin"} and inviter["role"] != "owner":
                raise HTTPException(403, "Invitation issuer is no longer an owner")
            connection.execute(_SQL_JOIN, (invite["tenant_id"], user["user_id"], invite["role"]))
            connection.execute(
                _SQL_AUDIT, (invite["tenant_id"], user["user_id"], "invite.accepted", invite["id"])
            )
            return {"tenant_id": invite["tenant_id"]}

    def invitations(self, principal: Principal) -> list:
        """Return scoped invite metadata without reusable secrets."""
        require_admin(principal)
        with self.db.auth() as connection:
            return connection.execute(_SQL_INVITATIONS, (principal.tenant_id,)).fetchall()

    def revoke(self, principal: Principal, invite_id: UUID):
        """Revoke only invitations owned by the authorised tenant."""
        require_admin(principal)
        with self.db.auth() as connection:
            self._lock_actor(connection, principal)
            if not connection.execute(_SQL_REVOKE, (principal.tenant_id, invite_id)).fetchone():
                raise HTTPException(404, "Invitation not found")

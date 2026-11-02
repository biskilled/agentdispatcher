"""Explicit AgentDesk account linking; remote tokens never become local sessions."""

from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import HTTPException
from pydantic import AwareDatetime, Field, ValidationError

from dispatcher.auth import member_principal
from dispatcher.contracts import Contract

_SQL_BIND = """
INSERT INTO mng_agentdesk_bindings(tenant_id,issuer,client_id,created_by)
VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING tenant_id
"""
_SQL_BINDING = "SELECT * FROM mng_agentdesk_bindings WHERE tenant_id=%s"
_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_REMOVE = "DELETE FROM mng_agentdesk_bindings WHERE tenant_id=%s"
_SQL_LINK = """
INSERT INTO mng_agentdesk_links(tenant_id,user_id,subject) VALUES(%s,%s,%s)
ON CONFLICT DO NOTHING RETURNING user_id
"""
_SQL_LINKED = "SELECT subject FROM mng_agentdesk_links WHERE tenant_id=%s AND user_id=%s"
_SQL_UNLINK = "DELETE FROM mng_agentdesk_links WHERE tenant_id=%s AND user_id=%s"
_SQL_MEMBER = "SELECT role FROM mng_memberships WHERE tenant_id=%s AND user_id=%s FOR SHARE"
_SQL_RESOLVE = """
SELECT l.user_id,m.role FROM mng_agentdesk_links l JOIN mng_memberships m
ON (m.tenant_id,m.user_id)=(l.tenant_id,l.user_id)
WHERE l.tenant_id=%s AND l.subject=%s
"""
_SQL_AUDIT = """
INSERT INTO mng_auth_audit(tenant_id,actor_id,action,target_id) VALUES(%s,%s,%s,%s)
"""


class RemoteIdentity(Contract):
    """Only a live human principal from the configured trusted server is accepted."""

    subject: str = Field(min_length=1, max_length=100)
    client_id: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "member", "viewer"]
    active: Literal[True]
    expires_at: AwareDatetime


class AgentDesk:
    """Use remote identity as proof, with local membership as the permission authority."""

    def __init__(self, auth, transport=None):
        self.auth, self.db, self.settings = auth, auth.db, auth.settings
        self.transport = transport

    @property
    def issuer(self):
        """Changing the operator-approved endpoint invalidates existing tenant bindings."""
        return self.settings.agentdesk_identity_url

    def verify(self, token: str) -> RemoteIdentity:
        """Introspect every request without redirects, credential caching or error-body logging."""
        if not self.issuer:
            raise HTTPException(503, "AgentDesk identity connection is not configured")
        if not token or token.startswith("ad_") or len(token) > self.settings.identity_max_bytes:
            raise HTTPException(401, "A human AgentDesk access token is required")
        try:
            with httpx.Client(
                timeout=self.settings.http_timeout, transport=self.transport
            ) as client:
                with client.stream(
                    "GET", self.issuer, headers={"Authorization": f"Bearer {token}"}
                ) as response:
                    if response.status_code in {401, 403}:
                        raise HTTPException(401, "AgentDesk identity is inactive or invalid")
                    if response.status_code != 200:
                        raise HTTPException(503, "AgentDesk identity verification unavailable")
                    body = bytearray()
                    for part in response.iter_bytes():
                        body.extend(part)
                        if len(body) > self.settings.identity_max_bytes:
                            raise HTTPException(503, "Invalid AgentDesk identity response")
            identity = RemoteIdentity.model_validate_json(bytes(body))
            if identity.expires_at <= datetime.now(UTC):
                raise HTTPException(401, "AgentDesk access token expired")
            return identity
        except (httpx.HTTPError, ValidationError) as error:
            raise HTTPException(503, "AgentDesk identity verification unavailable") from error

    def _binding(self, connection, tenant_id, identity=None):
        row = connection.execute(_SQL_BINDING, (tenant_id,)).fetchone()
        if not row or row["issuer"] != self.issuer:
            raise HTTPException(403, "This workspace has no matching AgentDesk tenant binding")
        if identity and row["client_id"] != identity.client_id:
            raise HTTPException(403, "AgentDesk tenant does not match this workspace")
        return row

    def _actor(self, connection, principal, owner=False):
        connection.execute(_SQL_LOCK, (f"{principal.tenant_id}:agentdesk",))
        row = connection.execute(
            _SQL_MEMBER, (principal.tenant_id, principal.subject_id)
        ).fetchone()
        if not row or (owner and row["role"] != "owner"):
            raise HTTPException(403, "Workspace owner required" if owner else "Membership required")

    def _audit(self, connection, principal, action):
        connection.execute(
            _SQL_AUDIT,
            (
                principal.tenant_id,
                principal.subject_id,
                action,
                principal.subject_id,
            ),
        )

    def status(self, principal):
        """Return safe connection metadata and only this person's account link."""
        with self.db.auth() as connection:
            binding = connection.execute(_SQL_BINDING, (principal.tenant_id,)).fetchone()
            link = connection.execute(
                _SQL_LINKED, (principal.tenant_id, principal.subject_id)
            ).fetchone()
        return {
            "configured": bool(self.issuer),
            "bound": bool(binding and binding["issuer"] == self.issuer),
            "client_id": binding["client_id"] if binding else None,
            "linked": bool(link),
        }

    def bind(self, principal, token):
        """Require an owner here and an administrator there; never infer tenants from email."""
        if principal.role != "owner":
            raise HTTPException(403, "Workspace owner required")
        identity = self.verify(token)
        if identity.role != "admin":
            raise HTTPException(403, "AgentDesk tenant administrator required")
        with self.db.auth() as connection:
            self._actor(connection, principal, owner=True)
            inserted = connection.execute(
                _SQL_BIND,
                (
                    principal.tenant_id,
                    self.issuer,
                    identity.client_id,
                    principal.subject_id,
                ),
            ).fetchone()
            if not inserted:
                self._binding(connection, principal.tenant_id, identity)
            self._audit(connection, principal, "agentdesk.bound")

    def link(self, principal, token):
        """Link only the signed-in user's existing membership; no auto-provision or email merge."""
        identity = self.verify(token)
        with self.db.auth() as connection:
            self._actor(connection, principal)
            self._binding(connection, principal.tenant_id, identity)
            added = connection.execute(
                _SQL_LINK,
                (
                    principal.tenant_id,
                    principal.subject_id,
                    identity.subject,
                ),
            ).fetchone()
            if not added:
                existing = connection.execute(
                    _SQL_LINKED,
                    (
                        principal.tenant_id,
                        principal.subject_id,
                    ),
                ).fetchone()
                if not existing or existing["subject"] != identity.subject:
                    raise HTTPException(409, "Account already linked; unlink before replacing it")
            self._audit(connection, principal, "agentdesk.linked")

    def disconnect(self, principal, tenant=False):
        """Unlink a personal account or, for an owner, remove the binding and all its links."""
        with self.db.auth() as connection:
            self._actor(connection, principal, owner=tenant)
            connection.execute(
                _SQL_REMOVE if tenant else _SQL_UNLINK,
                (principal.tenant_id,) if tenant else (principal.tenant_id, principal.subject_id),
            )
            self._audit(
                connection, principal, "agentdesk.disconnected" if tenant else "agentdesk.unlinked"
            )

    def principal(self, token, tenant_id):
        """Check live remote identity plus local membership and grants on every tool request."""
        identity = self.verify(token)
        with self.db.auth() as connection:
            self._binding(connection, tenant_id, identity)
            row = connection.execute(_SQL_RESOLVE, (tenant_id, identity.subject)).fetchone()
            if not row:
                raise HTTPException(403, "Link your existing workspace account first")
            # A remote role can reduce, but never increase, local permissions.
            role = row["role"]
            if identity.role == "viewer":
                role = "viewer"
            elif identity.role != "admin" and role in {"owner", "admin"}:
                role = "member"
            return member_principal(connection, tenant_id, row["user_id"], role)

"""Human sessions and scoped service credentials with one permission boundary."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException

from dispatcher.contracts import Principal
from dispatcher.db import Database

_SQL_LOGIN_IDENTITY = "SELECT user_id FROM mng_identities WHERE issuer=%s AND subject=%s"
_SQL_LOGIN_LIMIT = """
INSERT INTO mng_login_limits(identity_hash, window_start, requests) VALUES (%s, now(), 1)
ON CONFLICT (identity_hash) DO UPDATE SET
  requests = CASE WHEN mng_login_limits.window_start < now() - %s * interval '1 second'
                  THEN 1 ELSE mng_login_limits.requests + 1 END,
  window_start = CASE WHEN mng_login_limits.window_start < now() - %s * interval '1 second'
                      THEN now() ELSE mng_login_limits.window_start END
RETURNING requests
"""
_SQL_LOGIN_ADD = "INSERT INTO mng_login_tokens(token_hash,user_id,expires_at) VALUES (%s,%s,%s)"
_SQL_LOGIN_CONSUME = """
UPDATE mng_login_tokens SET used_at=now()
WHERE token_hash=%s AND used_at IS NULL AND expires_at > now() RETURNING user_id
"""
_SQL_SESSION_ADD = "INSERT INTO mng_sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)"
_SQL_SESSION = """
SELECT s.user_id, u.email, s.created_at FROM mng_sessions s JOIN mng_users u ON u.id=s.user_id
WHERE s.token_hash=%s AND s.expires_at > now()
"""
_SQL_LOGOUT = "DELETE FROM mng_sessions WHERE token_hash=%s"
_SQL_MEMBERSHIPS = """
SELECT m.tenant_id, t.name, m.role FROM mng_memberships m
JOIN mng_tenants t ON t.id=m.tenant_id WHERE m.user_id=%s ORDER BY t.name
"""
_SQL_MEMBERSHIP = "SELECT role FROM mng_memberships WHERE user_id=%s AND tenant_id=%s"
_SQL_KEY_ADD = """
INSERT INTO mng_sdk_keys(id,tenant_id,token_hash,name,app,environment,created_by,expires_at)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_KEY_AUTH = """
UPDATE mng_sdk_keys SET last_used_at=now()
WHERE token_hash=%s AND revoked_at IS NULL AND expires_at > now()
AND purpose='ingest'
RETURNING id,tenant_id,app,environment,expires_at
"""
_SQL_KEY_LIST = """
SELECT id,name,app,environment,created_at,expires_at,revoked_at,last_used_at
FROM mng_sdk_keys WHERE tenant_id=%s AND purpose='ingest' ORDER BY created_at DESC
"""
_SQL_KEY_REVOKE = """
UPDATE mng_sdk_keys SET revoked_at=now() WHERE id=%s AND tenant_id=%s RETURNING id
"""
_SQL_AUDIT = """
INSERT INTO mng_auth_audit(tenant_id,actor_id,action,target_id) VALUES (%s,%s,%s,%s)
"""
_SQL_USER_ADD = "INSERT INTO mng_users(id,email) VALUES (%s,%s)"
_SQL_IDENTITY_ADD = "INSERT INTO mng_identities(issuer,subject,user_id) VALUES (%s,%s,%s)"
_SQL_IDENTITY_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
_SQL_GRANTS = "SELECT app FROM mng_view_grants WHERE tenant_id=%s AND user_id=%s"
_SQL_DELEGATE = """
INSERT INTO mng_delegations(token_hash,tenant_id,user_id,app,session_hash,expires_at)
VALUES(%s,%s,%s,%s,%s,%s)
"""
_SQL_DELEGATION = """
SELECT d.user_id FROM mng_delegations d JOIN mng_sessions s ON s.token_hash=d.session_hash
JOIN mng_memberships m ON (m.tenant_id,m.user_id)=(d.tenant_id,d.user_id)
WHERE d.token_hash=%s AND d.tenant_id=%s AND d.app=%s AND d.expires_at>now()
AND s.expires_at>now()
"""
_SQL_OIDC_START = "INSERT INTO mng_oidc_flows(state_hash,expires_at) VALUES(%s,%s)"
_SQL_OIDC_CONSUME = """
UPDATE mng_oidc_flows SET used_at=now() WHERE state_hash=%s AND expires_at>now()
AND used_at IS NULL RETURNING state_hash
"""


def verifier(secret: str) -> str:
    """Hash high-entropy bearer secrets, never human passwords."""
    return hashlib.sha256(secret.encode()).hexdigest()


def require_admin(principal: Principal) -> None:
    """Reject service keys and non-admin human roles at the shared boundary."""
    if principal.role not in {"owner", "admin"}:
        raise HTTPException(403, "Tenant administrator access required")


def validate_scope(principal: Principal, event) -> None:
    """Prevent a key for one app/environment from submitting another app's records."""
    if principal.role != "service":
        raise HTTPException(403, "SDK key required")
    if (event.app, event.environment) != (principal.app, principal.environment):
        raise HTTPException(403, "Event is outside the SDK key scope")
    if getattr(event, "tenant_id", None) not in (None, principal.tenant_id):
        raise HTTPException(403, "Event tenant does not match SDK key")


def require_usage_reader(principal: Principal) -> None:
    """Members read their verified usage; viewers need an explicit app grant."""
    if principal.role == "service" or (principal.role == "viewer" and not principal.visible_apps):
        raise HTTPException(403, "Usage view permission required")


def usage_scope(principal: Principal) -> tuple:
    """Resolve broad, granted-app and own-user visibility from verified identity only."""
    return (
        principal.role in {"owner", "admin"} or "*" in principal.visible_apps,
        principal.visible_apps,
        principal.subject_id if principal.role == "member" else None,
    )


class AuthService:
    """Resolve credentials from private auth tables without accepting claimed tenant tags."""

    def __init__(self, db: Database):
        self.db = db
        self.settings = db.settings

    def new_secret(self) -> str:
        """Generate a cryptographically random bearer token."""
        return secrets.token_urlsafe(self.settings.secret_bytes)

    def request_login(self, email: str, requester: str) -> str | None:
        """Create a short-lived email token only for an existing email identity."""
        with self.db.auth() as connection:
            allowed = True
            for identifier in ("email:" + email, "ip:" + requester):
                window = self.settings.login_window_seconds
                row = connection.execute(
                    _SQL_LOGIN_LIMIT, (verifier(identifier), window, window)
                ).fetchone()
                allowed &= row["requests"] <= self.settings.login_requests_per_window
            row = connection.execute(_SQL_LOGIN_IDENTITY, ("email", email)).fetchone()
            if not allowed or row is None:
                return None
            token = self.new_secret()
            expires = datetime.now(UTC) + timedelta(seconds=self.settings.login_seconds)
            connection.execute(_SQL_LOGIN_ADD, (verifier(token), row["user_id"], expires))
            return token

    def consume_login(self, token: str) -> str:
        """Consume once and create the session in the same transaction."""
        with self.db.auth() as connection:
            row = connection.execute(_SQL_LOGIN_CONSUME, (verifier(token),)).fetchone()
            if row is None:
                raise HTTPException(401, "Invalid or expired sign-in link")
            return self._session(connection, row["user_id"])

    def _session(self, connection, user_id: UUID) -> str:
        token = self.new_secret()
        expires = datetime.now(UTC) + timedelta(seconds=self.settings.session_seconds)
        connection.execute(_SQL_SESSION_ADD, (verifier(token), user_id, expires))
        return token

    def user(self, session: str) -> dict:
        """Load an unexpired session; deleted sessions take effect on the next request."""
        with self.db.auth() as connection:
            row = connection.execute(_SQL_SESSION, (verifier(session),)).fetchone()
            if row is None:
                raise HTTPException(401, "Sign in required")
            row["tenants"] = connection.execute(_SQL_MEMBERSHIPS, (row["user_id"],)).fetchall()
            return row

    def human(self, session: str, tenant_id: UUID) -> Principal:
        """Recheck membership on every request, independent of selected browser tenant."""
        user = self.user(session)
        with self.db.auth() as connection:
            membership = connection.execute(
                _SQL_MEMBERSHIP, (user["user_id"], tenant_id)
            ).fetchone()
            grants = connection.execute(_SQL_GRANTS, (tenant_id, user["user_id"])).fetchall()
        if membership is None:
            raise HTTPException(403, "Tenant membership required")
        return Principal(
            tenant_id=tenant_id,
            subject_id=user["user_id"],
            role=membership["role"],
            visible_apps=[row["app"] for row in grants],
        )

    def recent_user(self, session: str) -> dict:
        """Require recent sign-in before binding an additional identity."""
        user = self.user(session)
        if (datetime.now(UTC) - user["created_at"]).total_seconds() > self.settings.reauth_seconds:
            raise HTTPException(401, "Sign in again before linking an account")
        return user

    def start_oidc(self, state: str) -> None:
        """Persist a single-use state verifier independently of the signed browser cookie."""
        expiry = datetime.now(UTC) + timedelta(seconds=self.settings.login_seconds)
        with self.db.auth() as connection:
            connection.execute(_SQL_OIDC_START, (verifier(state), expiry))

    def consume_oidc(self, state: str) -> None:
        """Reject replays even when an old signed OAuth cookie is restored."""
        with self.db.auth() as connection:
            if not connection.execute(_SQL_OIDC_CONSUME, (verifier(state),)).fetchone():
                raise HTTPException(401, "Invalid or replayed sign-in state")

    def delegate(self, session: str, tenant_id: UUID, app: str) -> dict:
        """Issue short-lived consent for a service to attribute requests to this user."""
        principal = self.human(session, tenant_id)
        secret = self.new_secret()
        expiry = datetime.now(UTC) + timedelta(seconds=self.settings.delegation_seconds)
        with self.db.auth() as connection:
            connection.execute(
                _SQL_DELEGATE,
                (verifier(secret), tenant_id, principal.subject_id, app, verifier(session), expiry),
            )
        return {"token": secret, "expires_at": expiry, "app": app}

    def delegated(self, principal: Principal, token: str) -> Principal:
        """Bind a service request to a still-valid user session, tenant, and app."""
        with self.db.auth() as connection:
            row = connection.execute(
                _SQL_DELEGATION, (verifier(token), principal.tenant_id, principal.app)
            ).fetchone()
        if not row:
            raise HTTPException(401, "Invalid or expired user delegation")
        return principal.model_copy(update={"verified_user_id": row["user_id"]})

    def service(self, token: str) -> Principal:
        """Authenticate ingest-only credentials without caching revocation state."""
        with self.db.auth() as connection:
            row = connection.execute(_SQL_KEY_AUTH, (verifier(token),)).fetchone()
        if row is None:
            raise HTTPException(401, "Invalid or expired SDK key")
        return Principal(
            tenant_id=row["tenant_id"],
            subject_id=row["id"],
            role="service",
            app=row["app"],
            environment=row["environment"],
            expires_at=row["expires_at"],
        )

    def issue_key(self, principal: Principal, name: str, app: str, environment: str) -> dict:
        """Return the secret once; persist only its verifier and scope."""
        require_admin(principal)
        key_id, secret = uuid4(), self.new_secret()
        expires = datetime.now(UTC) + timedelta(seconds=self.settings.key_seconds)
        with self.db.auth() as connection:
            connection.execute(
                _SQL_KEY_ADD,
                (
                    key_id,
                    principal.tenant_id,
                    verifier(secret),
                    name,
                    app,
                    environment,
                    principal.subject_id,
                    expires,
                ),
            )
            connection.execute(
                _SQL_AUDIT, (principal.tenant_id, principal.subject_id, "key.created", key_id)
            )
        return {"id": key_id, "secret": secret, "expires_at": expires}

    def keys(self, principal: Principal) -> list[dict]:
        """Return scoped metadata, never stored verifiers or original secrets."""
        require_admin(principal)
        with self.db.auth() as connection:
            return connection.execute(_SQL_KEY_LIST, (principal.tenant_id,)).fetchall()

    def revoke_key(self, principal: Principal, key_id: UUID) -> None:
        """Revoke only a key owned by the administrator's verified tenant."""
        require_admin(principal)
        with self.db.auth() as connection:
            row = connection.execute(_SQL_KEY_REVOKE, (key_id, principal.tenant_id)).fetchone()
            if row is None:
                raise HTTPException(404, "Key not found")
            connection.execute(
                _SQL_AUDIT, (principal.tenant_id, principal.subject_id, "key.revoked", key_id)
            )

    def logout(self, token: str) -> None:
        """Invalidate server-side session state immediately."""
        with self.db.auth() as connection:
            connection.execute(_SQL_LOGOUT, (verifier(token),))

    def google_login(self, claims: dict, link_user: UUID | None = None) -> str:
        """Accept only library-verified claims; never merge users by email address."""
        if not claims.get("email_verified") or not claims.get("sub"):
            raise HTTPException(401, "Verified Google identity required")
        issuer, subject = claims["iss"], claims["sub"]
        with self.db.auth() as connection:
            connection.execute(_SQL_IDENTITY_LOCK, (issuer + ":" + subject,))
            row = connection.execute(_SQL_LOGIN_IDENTITY, (issuer, subject)).fetchone()
            if row and link_user and row["user_id"] != link_user:
                raise HTTPException(409, "This Google identity is already linked")
            user_id = row["user_id"] if row else link_user or uuid4()
            if row is None:
                if link_user is None:
                    connection.execute(_SQL_USER_ADD, (user_id, claims["email"]))
                connection.execute(_SQL_IDENTITY_ADD, (issuer, subject, user_id))
            return self._session(connection, user_id)

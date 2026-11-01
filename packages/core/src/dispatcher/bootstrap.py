"""Operator-only provisioning; tenant ownership is never inferred from public signup."""

from uuid import uuid4

from dispatcher.contracts import Principal
from dispatcher.db import Database

_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
_SQL_IDENTITY = "SELECT user_id FROM mng_identities WHERE issuer='email' AND subject=%s"
_SQL_USER = "INSERT INTO mng_users(id,email) VALUES (%s,%s)"
_SQL_LINK = "INSERT INTO mng_identities(issuer,subject,user_id) VALUES ('email',%s,%s)"
_SQL_TENANT = "INSERT INTO mng_tenants(id,name) VALUES (%s,%s)"
_SQL_MEMBER = "INSERT INTO mng_memberships(tenant_id,user_id,role) VALUES (%s,%s,'owner')"


def create_tenant(db: Database, name: str, email: str) -> Principal:
    """Provision an owner; they must still prove mailbox control before signing in."""
    from dispatcher.api import EmailRequest

    email = EmailRequest(email=email).email.lower()
    tenant_id = uuid4()
    with db.auth() as connection:
        connection.execute(_SQL_LOCK, (email,))
        row = connection.execute(_SQL_IDENTITY, (email,)).fetchone()
        user_id = row["user_id"] if row else uuid4()
        if row is None:
            connection.execute(_SQL_USER, (user_id, email))
            connection.execute(_SQL_LINK, (email, user_id))
        connection.execute(_SQL_TENANT, (tenant_id, name))
        connection.execute(_SQL_MEMBER, (tenant_id, user_id))
    return Principal(tenant_id=tenant_id, subject_id=user_id, role="owner")

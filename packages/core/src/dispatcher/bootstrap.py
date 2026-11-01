"""Operator-only provisioning; tenant ownership is never inferred from public signup."""

from uuid import uuid4

from dispatcher.contracts import Principal
from dispatcher.db import Database
from dispatcher.membership import ensure_email_identity

_SQL_TENANT = "INSERT INTO mng_tenants(id,name) VALUES (%s,%s)"
_SQL_MEMBER = "INSERT INTO mng_memberships(tenant_id,user_id,role) VALUES (%s,%s,'owner')"


def create_tenant(db: Database, name: str, email: str) -> Principal:
    """Provision an owner; they must still prove mailbox control before signing in."""
    from dispatcher.api import EmailRequest

    email = EmailRequest(email=email).email.lower()
    tenant_id = uuid4()
    with db.auth() as connection:
        user_id = ensure_email_identity(connection, email)
        connection.execute(_SQL_TENANT, (tenant_id, name))
        connection.execute(_SQL_MEMBER, (tenant_id, user_id))
    return Principal(tenant_id=tenant_id, subject_id=user_id, role="owner")

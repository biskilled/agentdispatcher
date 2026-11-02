"""Deployment-only provisioning of individually revocable analytics credentials."""

from uuid import UUID, uuid4

import psycopg
from psycopg import sql

_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_TENANT = "SELECT id FROM mng_tenants WHERE id=%s"
_SQL_ROLE = "SELECT oid FROM pg_roles WHERE rolname=%s"
_SQL_BINDING = "SELECT tenant_id FROM mng_analytics_roles WHERE role_oid=%s"
_SQL_CREATE = sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
_SQL_PASSWORD = sql.SQL("ALTER ROLE {} PASSWORD {}")
_SQL_GRANT = sql.SQL("GRANT dispatcher_analytics TO {}")
_SQL_BIND = """
INSERT INTO mng_analytics_roles(role_oid,tenant_id) VALUES (%s,%s)
ON CONFLICT(role_oid) DO UPDATE SET enabled=true
"""
_SQL_REVOKE = "UPDATE mng_analytics_roles SET enabled=false WHERE tenant_id=%s"


def provision(dsn: str, tenant_id: UUID, password: str, *, new_login: bool = False) -> str:
    """Create/rotate one tenant login using the migration credential, never runtime privileges."""
    if len(password) < 32:
        raise ValueError("Analytics passwords must contain at least 32 characters")
    role = "dispatcher_ro_" + (uuid4().hex if new_login else tenant_id.hex)
    with psycopg.connect(dsn) as connection:
        connection.execute(_SQL_LOCK, ("analytics:" + str(tenant_id),))
        if not connection.execute(_SQL_TENANT, (tenant_id,)).fetchone():
            raise ValueError("Tenant does not exist")
        existing = connection.execute(_SQL_ROLE, (role,)).fetchone()
        if existing:
            binding = connection.execute(_SQL_BINDING, (existing[0],)).fetchone()
            if not binding or binding[0] != tenant_id:
                raise ValueError("Existing database role is not this tenant's managed credential")
        else:
            connection.execute(_SQL_CREATE.format(sql.Identifier(role)))
        if new_login:
            # Recovery must not adopt a stale cluster-local OID or alter another database's login.
            connection.execute(_SQL_REVOKE, (tenant_id,))
        # PostgreSQL role DDL cannot bind PASSWORD as a query parameter. psycopg Literal
        # quotes this value as data; it is never interpolated into an SQL string.
        connection.execute(_SQL_PASSWORD.format(sql.Identifier(role), sql.Literal(password)))
        connection.execute(_SQL_GRANT.format(sql.Identifier(role)))
        oid = connection.execute(_SQL_ROLE, (role,)).fetchone()[0]
        connection.execute(_SQL_BIND, (oid, tenant_id))
    return role


def revoke(dsn: str, tenant_id: UUID) -> None:
    """Remove read access for existing and future connections, including pooled sessions."""
    with psycopg.connect(dsn) as connection:
        connection.execute(_SQL_REVOKE, (tenant_id,))

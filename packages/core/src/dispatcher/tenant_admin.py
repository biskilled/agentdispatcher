"""Offline tenant erasure for deployment operators; never reachable through ingest credentials."""

import argparse
import json
import os
from uuid import UUID

import psycopg
from psycopg import sql

_SQL_OPERATOR = "SELECT rolsuper FROM pg_roles WHERE rolname=current_user"
_SQL_TENANT = "SELECT id FROM mng_tenants WHERE id=%s FOR UPDATE"
_SQL_TABLES = """
SELECT c.table_name FROM information_schema.columns c
JOIN information_schema.tables t USING(table_catalog,table_schema,table_name)
WHERE c.table_schema='public' AND c.column_name='tenant_id' AND t.table_type='BASE TABLE'
AND (c.table_name LIKE 'mng_%' OR c.table_name LIKE 'mem_%') ORDER BY c.table_name
"""
_SQL_DEPENDENCIES = """
SELECT child.relname,parent.relname FROM pg_constraint dependency
JOIN pg_class child ON child.oid=dependency.conrelid
JOIN pg_class parent ON parent.oid=dependency.confrelid
JOIN pg_namespace child_schema ON child_schema.oid=child.relnamespace
JOIN pg_namespace parent_schema ON parent_schema.oid=parent.relnamespace
WHERE dependency.contype='f' AND child_schema.nspname='public' AND parent_schema.nspname='public'
"""
_SQL_DELETE = sql.SQL("DELETE FROM public.{} WHERE tenant_id=%s")
_SQL_DELETE_TENANT = "DELETE FROM mng_tenants WHERE id=%s"


def deletion_order(tables, dependencies):
    """Order trusted schema identifiers by foreign keys; refuse unknown cycles before deletion."""
    pending, ordered = set(tables), []
    while pending:
        leaves = sorted(
            table
            for table in pending
            if not any(
                parent == table and child in pending and child != parent
                for child, parent in dependencies
            )
        )
        if not leaves:
            raise ValueError("Tenant schema has a dependency cycle; operator migration is required")
        ordered.extend(leaves)
        pending.difference_update(leaves)
    return ordered


def delete_tenant(dsn, tenant_id, confirmation):
    """Erase only the confirmed tenant atomically; shared users and other tenants remain intact."""
    if not isinstance(tenant_id, UUID) or confirmation != tenant_id:
        raise ValueError("Explicit matching tenant UUID confirmation is required")
    with psycopg.connect(dsn) as connection:
        if not connection.execute(_SQL_OPERATOR).fetchone()[0]:
            raise ValueError("Tenant erasure requires an offline PostgreSQL operator")
        if not connection.execute(_SQL_TENANT, (tenant_id,)).fetchone():
            raise ValueError("Tenant does not exist")
        tables = [row[0] for row in connection.execute(_SQL_TABLES)]
        dependencies = connection.execute(_SQL_DEPENDENCIES).fetchall()
        counts = {}
        for table in deletion_order(tables, dependencies):
            counts[table] = connection.execute(
                _SQL_DELETE.format(sql.Identifier(table)), (tenant_id,)
            ).rowcount
        connection.execute(_SQL_DELETE_TENANT, (tenant_id,))
    return {
        "deleted_tenant": str(tenant_id),
        "deleted_rows": counts,
        "shared_identities": "Retained because users may belong to other tenants",
    }


def main():
    """Require an operator environment and a repeated tenant UUID for irreversible deletion."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True, type=UUID)
    parser.add_argument("--confirm-tenant", required=True, type=UUID)
    args = parser.parse_args()
    print(
        json.dumps(
            delete_tenant(
                os.environ["DISPATCHER_RECOVERY_DATABASE_URL"], args.tenant, args.confirm_tenant
            )
        )
    )


if __name__ == "__main__":
    main()

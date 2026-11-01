"""Database boundaries: private identity store and tenant-scoped runtime transactions."""

from contextlib import contextmanager
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from dispatcher.migrations import MIGRATIONS
from dispatcher.settings import Settings

_SQL_TENANT = "SELECT set_config('dispatcher.tenant_id', %s, true)"
_SQL_ROLE = "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
_SQL_READY = "SELECT version FROM mng_migrations ORDER BY version DESC LIMIT 1"


class Database:
    """Keep auth credentials separate from tenant data credentials."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def auth(self):
        """Open a transaction restricted to identity tables by database grants."""
        with psycopg.connect(
            self.settings.auth_database_url.get_secret_value(), row_factory=dict_row
        ) as connection:
            yield connection

    @contextmanager
    def tenant(self, tenant_id: UUID):
        """Bind server-verified scope for one transaction; local state cannot leak."""
        with psycopg.connect(
            self.settings.database_url.get_secret_value(), row_factory=dict_row
        ) as connection:
            role = connection.execute(_SQL_ROLE).fetchone()
            if role["rolsuper"] or role["rolbypassrls"]:
                raise RuntimeError("Tenant database role must not bypass row-level security")
            connection.execute(_SQL_TENANT, (str(tenant_id),))
            yield connection

    def ready(self) -> bool:
        """Check migrations without reading any tenant data."""
        with self.auth() as connection:
            applied = connection.execute(_SQL_READY).fetchone()
            return bool(applied and applied["version"] >= MIGRATIONS[-1][0])

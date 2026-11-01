"""Deployment-only migration and login provisioning; runtime never receives the owner DSN."""

import os

import psycopg
from dispatcher.migrations import migrate

_SQL_APP_PASSWORD = "ALTER ROLE dispatcher_app LOGIN PASSWORD %s"
_SQL_AUTH_PASSWORD = "ALTER ROLE dispatcher_auth LOGIN PASSWORD %s"
_SQL_GATEWAY_PASSWORD = "ALTER ROLE dispatcher_gateway LOGIN PASSWORD %s"


def main() -> None:
    """Migrate and bind externally supplied role passwords with client-side parameters."""
    dsn = os.environ["DISPATCHER_MIGRATION_DATABASE_URL"]
    migrate(dsn)
    with psycopg.connect(dsn, cursor_factory=psycopg.ClientCursor) as connection:
        connection.execute(_SQL_APP_PASSWORD, (os.environ["DISPATCHER_APP_DB_PASSWORD"],))
        connection.execute(_SQL_AUTH_PASSWORD, (os.environ["DISPATCHER_AUTH_DB_PASSWORD"],))
        if os.environ.get("DISPATCHER_GATEWAY_DB_PASSWORD"):
            connection.execute(
                _SQL_GATEWAY_PASSWORD, (os.environ["DISPATCHER_GATEWAY_DB_PASSWORD"],)
            )


if __name__ == "__main__":
    main()

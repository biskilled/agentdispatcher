"""Operator-only consistent backups and empty-database recovery, separate from runtime access."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from dispatcher.migrations import _SQL_LOCK, MIGRATIONS, migrate

_SQL_VERSIONS = "SELECT version FROM mng_migrations ORDER BY version"
_SQL_EMPTY = "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
_SQL_SUPERUSER = "SELECT rolsuper FROM pg_roles WHERE rolname=current_user"
_SQL_DENY_CONNECT = sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC")
_SQL_ALLOW_CONNECT = sql.SQL(
    "GRANT CONNECT ON DATABASE {} TO dispatcher_app,dispatcher_auth,dispatcher_analytics"
)
_SQL_INVALIDATE = """
DELETE FROM mng_sessions;
DELETE FROM mng_login_tokens;
DELETE FROM mng_oidc_flows;
UPDATE mng_sdk_keys SET revoked_at=COALESCE(revoked_at,now());
UPDATE mng_invitations SET revoked_at=COALESCE(revoked_at,now());
"""
_ENV_FIELDS = {
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "port": "PGPORT",
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "sslmode": "PGSSLMODE",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslrootcert": "PGSSLROOTCERT",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "options": "PGOPTIONS",
    "service": "PGSERVICE",
    "application_name": "PGAPPNAME",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
}
_EXCLUDED = ("mng_migrations", "mng_analytics_roles")


def private_file(path):
    """Create without overwrite or symlink following; database backups contain sensitive records."""
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")


def digest(path):
    """Hash incrementally so backup size is not constrained by process memory."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class Recovery:
    """Use an operator-supplied owner DSN; never expose it through API endpoints or arguments."""

    def __init__(self, dsn, *, pg_dump="pg_dump", pg_restore="pg_restore"):
        self.dsn, self.pg_dump, self.pg_restore = dsn, pg_dump, pg_restore

    def _environment(self):
        values = conninfo_to_dict(self.dsn)
        if values.keys() - _ENV_FIELDS.keys():
            raise ValueError("Recovery DSN contains unsupported libpq options")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        environment.update({_ENV_FIELDS[key]: value for key, value in values.items()})
        return environment

    def _run(self, command, *, output=None):
        result = subprocess.run(
            command,
            env=self._environment(),
            stdout=output or subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            # pg_restore errors can include row values; never log arbitrary database contents.
            raise RuntimeError(
                "PostgreSQL recovery failed; verify client/server versions and operator permissions"
            )

    def backup(self, path):
        """Write a consistent archive and checksum manifest; exclude cluster-local role IDs."""
        path = Path(path)
        manifest = path.with_name(path.name + ".json")
        if manifest.exists():
            raise FileExistsError("Backup manifest already exists")
        with psycopg.connect(self.dsn) as connection:
            # Share the migration lock while pg_dump takes its own consistent data snapshot.
            connection.execute(_SQL_LOCK)
            versions = [row[0] for row in connection.execute(_SQL_VERSIONS)]
            if versions != [version for version, _ in MIGRATIONS]:
                raise ValueError("Run the backup with the code version matching the source schema")
            with private_file(path) as target:
                self._run(
                    [
                        self.pg_dump,
                        "--format=custom",
                        "--data-only",
                        "--no-owner",
                        *["--exclude-table-data=public." + name for name in _EXCLUDED],
                    ],
                    output=target,
                )
        with private_file(manifest) as target:
            target.write(
                json.dumps(
                    {
                        "format": 1,
                        "versions": versions,
                        "sha256": digest(path),
                        "excluded": list(_EXCLUDED),
                    }
                ).encode()
            )
        return {"archive": str(path), "manifest": str(manifest), "versions": versions}

    def restore(self, path):
        """Restore only into an empty database; invalidate restored credentials before use."""
        path = Path(path)
        manifest = json.loads(path.with_name(path.name + ".json").read_text())
        if (
            manifest.get("format") != 1
            or manifest.get("versions") != [version for version, _ in MIGRATIONS]
            or manifest.get("excluded") != list(_EXCLUDED)
            or manifest.get("sha256") != digest(path)
        ):
            raise ValueError("Backup checksum or schema version does not match this installation")
        with psycopg.connect(self.dsn) as connection:
            if connection.execute(_SQL_EMPTY).fetchone()[0]:
                raise ValueError(
                    "Restore requires a new empty database; existing data is never replaced"
                )
            if not connection.execute(_SQL_SUPERUSER).fetchone()[0]:
                raise ValueError("Offline recovery requires a PostgreSQL operator superuser")
            database = sql.Identifier(conninfo_to_dict(self.dsn)["dbname"])
            connection.execute(_SQL_DENY_CONNECT.format(database))
        migrate(self.dsn)
        self._run(
            [
                self.pg_restore,
                "--data-only",
                "--disable-triggers",
                "--single-transaction",
                "--exit-on-error",
                "--no-owner",
                "--dbname",
                conninfo_to_dict(self.dsn)["dbname"],
                str(path),
            ]
        )
        with psycopg.connect(self.dsn) as connection:
            connection.execute(_SQL_INVALIDATE)
            connection.execute(_SQL_ALLOW_CONNECT.format(database))
        return {
            "restored": True,
            "credentials_invalidated": True,
            "analytics_credentials": "Reprovision against the restored cluster",
        }


def main():
    """Read the operator DSN from a private environment, never command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    recovery = Recovery(
        os.environ["DISPATCHER_RECOVERY_DATABASE_URL"],
        pg_dump=os.environ.get("DISPATCHER_PG_DUMP", "pg_dump"),
        pg_restore=os.environ.get("DISPATCHER_PG_RESTORE", "pg_restore"),
    )
    print(json.dumps(getattr(recovery, args.action)(args.archive)))


if __name__ == "__main__":
    main()

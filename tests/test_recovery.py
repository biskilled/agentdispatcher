"""Restore real PostgreSQL archives into disposable databases and recheck runtime RLS."""

import os
import secrets
import shutil
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from dispatcher.analytics import provision
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.contracts import UsageEvent
from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.migrations import migrate
from dispatcher.recovery import Recovery
from fastapi import HTTPException
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr
from test_integration import event

_SQL_CREATE = sql.SQL("CREATE DATABASE {}")
_SQL_DROP = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)")
_SQL_SESSIONS = "SELECT count(*) FROM mng_sessions"
_SQL_ANALYTICS = "SELECT count(*) FROM mng_analytics_roles"
_SQL_ANALYTICS_USAGE = "SELECT count(*) FROM llm_usage"
_SQL_DROP_ROLE = sql.SQL("DROP ROLE {}")


def database_for(settings, dsn):
    """Use non-bypass runtime roles in both original and restored fixture databases."""
    return Database(
        settings.model_copy(
            update={
                "database_url": SecretStr(make_conninfo(dsn, user="dispatcher_app")),
                "auth_database_url": SecretStr(make_conninfo(dsn, user="dispatcher_auth")),
            }
        )
    )


def test_backup_restore_ownership_credentials_and_no_overwrite(settings, tmp_path):
    pg_dump = os.environ.get("DISPATCHER_PG_DUMP") or shutil.which("pg_dump")
    pg_restore = os.environ.get("DISPATCHER_PG_RESTORE") or shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        pytest.skip("Install matching PostgreSQL client tools to exercise recovery")
    base = os.environ["TEST_DATABASE_URL"]
    names = ["dispatcher_recovery_" + uuid4().hex for _ in range(2)]
    dsns = [make_conninfo(base, dbname=name) for name in names]
    analytics_roles = []
    with psycopg.connect(base, autocommit=True) as administration:
        try:
            for name in names:
                administration.execute(_SQL_CREATE.format(sql.Identifier(name)))
            migrate(dsns[0])
            source = database_for(settings, dsns[0])
            auth = AuthService(source)
            first_email = f"{uuid4().hex}@example.test"
            first = create_tenant(source, "Recovery A", first_email)
            auth.consume_login(auth.request_login(first_email, first_email))
            second = create_tenant(source, "Recovery B", f"{uuid4().hex}@example.test")
            key = auth.issue_key(first, "Fixture", "trader", "test")
            second_key = auth.issue_key(second, "Fixture", "trader", "test")
            analytics_roles.append(provision(dsns[0], first.tenant_id, secrets.token_urlsafe(32)))
            for credential, amount in ((key, "0.12"), (second_key, "0.34")):
                Ledger(source).ingest(
                    auth.service(credential["secret"]),
                    [
                        UsageEvent.model_validate(
                            event(reported_cost=amount, reported_currency="USD")
                        )
                    ],
                )
            archive = tmp_path / "backup.dump"
            Recovery(dsns[0], pg_dump=pg_dump).backup(archive)
            assert archive.stat().st_mode & 0o777 == 0o600
            with pytest.raises(FileExistsError):
                Recovery(dsns[0], pg_dump=pg_dump).backup(archive)
            with pytest.raises(ValueError, match="empty database"):
                Recovery(dsns[0], pg_restore=pg_restore).restore(archive)
            result = Recovery(dsns[1], pg_restore=pg_restore).restore(archive)
            assert result["credentials_invalidated"]
            restored = database_for(settings, dsns[1])
            assert str(Ledger(restored).events(first)[0]["cost"]) == "0.12"
            assert str(Ledger(restored).events(second)[0]["cost"]) == "0.34"
            with pytest.raises(HTTPException) as refused:
                AuthService(restored).service(key["secret"])
            assert refused.value.status_code == 401
            with psycopg.connect(dsns[1]) as connection:
                assert connection.execute(_SQL_SESSIONS).fetchone()[0] == 0
                assert connection.execute(_SQL_ANALYTICS).fetchone()[0] == 0
            with psycopg.connect(make_conninfo(dsns[1], user=analytics_roles[0])) as connection:
                assert connection.execute(_SQL_ANALYTICS_USAGE).fetchone()[0] == 0
            analytics_roles.append(
                provision(dsns[1], first.tenant_id, secrets.token_urlsafe(32), new_login=True)
            )
            assert analytics_roles[0] != analytics_roles[1]
            with psycopg.connect(make_conninfo(dsns[1], user=analytics_roles[1])) as connection:
                assert connection.execute(_SQL_ANALYTICS_USAGE).fetchone()[0] == 1
            manifest = Path(str(archive) + ".json")
            manifest.write_text(manifest.read_text().replace('"format": 1', '"format": 2'))
            with pytest.raises(ValueError, match="checksum or schema"):
                Recovery(dsns[1], pg_restore=pg_restore).restore(archive)
        finally:
            for name in names:
                administration.execute(_SQL_DROP.format(sql.Identifier(name)))
            for role in analytics_roles:
                administration.execute(_SQL_DROP_ROLE.format(sql.Identifier(role)))

"""Real PostgreSQL fixtures; configure a disposable database explicitly."""

import os
import secrets
from uuid import uuid4

import psycopg
import pytest
from dispatcher.api import create_app
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.db import Database
from dispatcher.migrations import migrate
from dispatcher.settings import Settings
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

_SQL_ROLE_APP = "ALTER ROLE dispatcher_app LOGIN"
_SQL_ROLE_AUTH = "ALTER ROLE dispatcher_auth LOGIN"


class TestMailer:
    """Capture delivery only in test fixtures, never expose a production debug route."""

    def __init__(self):
        self.tokens = []

    def send_login(self, email, token):
        """Keep the single-use token in memory for the test's explicit consume action."""
        self.tokens.append((email, token))


@pytest.fixture(scope="session")
def settings():
    """Apply idempotent migrations to an explicitly supplied disposable database."""
    owner = os.environ.get("TEST_DATABASE_URL")
    if not owner:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL owner connection")
    migrate(owner)
    migrate(owner)
    with psycopg.connect(owner) as connection:
        connection.execute(_SQL_ROLE_APP)
        connection.execute(_SQL_ROLE_AUTH)
    return Settings(
        database_url=make_conninfo(owner, user="dispatcher_app"),
        auth_database_url=make_conninfo(owner, user="dispatcher_auth"),
        public_url="http://testserver",
        secure_cookies=False,
        session_secret=secrets.token_urlsafe(32),
        smtp_host="test-mail",
        login_requests_per_window=1000,
    )


@pytest.fixture
def system(settings):
    """Give each test separate tenants without destructive shared database cleanup."""
    db = Database(settings)
    auth = AuthService(db)
    email = f"owner-{uuid4().hex}@example.test"
    owner = create_tenant(db, "Tenant A", email)
    other = create_tenant(db, "Tenant B", f"other-{uuid4().hex}@example.test")
    mailer = TestMailer()
    app = create_app(settings, mailer)
    with TestClient(app) as client:
        client.headers["Origin"] = settings.public_url
        client.post("/api/auth/email/request", json={"email": email})
        token = mailer.tokens[-1][1]
        response = client.post("/api/auth/email/consume", json={"token": token})
        assert response.status_code == 200
        client.headers["X-Tenant-ID"] = str(owner.tenant_id)
        key = client.post(
            "/api/keys", json={"name": "test", "app": "trader", "environment": "test"}
        ).json()
        yield {
            "db": db,
            "auth": auth,
            "owner": owner,
            "other": other,
            "client": client,
            "key": key,
            "token": token,
            "mailer": mailer,
            "email": email,
        }

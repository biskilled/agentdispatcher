"""Temporary passwords retain normal session, expiry, throttling and tenant boundaries."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from dispatcher.api import create_app
from dispatcher.auth import verifier
from dispatcher.passwords import hash_password, validate_password_hash, verify_password
from dispatcher.settings import Settings
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

_SQL_SESSION_EXPIRY = "SELECT expires_at FROM mng_sessions WHERE token_hash=%s"
_SQL_EXPIRE_SESSION = "UPDATE mng_sessions SET expires_at=now() WHERE token_hash=%s"
_SQL_USER_COUNT = "SELECT count(*) n FROM mng_users"


@pytest.fixture(scope="module")
def password_hash():
    return hash_password("A synthetic test password")


def configured(system, password_hash, **overrides):
    """Build validated per-test settings without modifying the shared fixture instance."""
    values = system["db"].settings.model_dump()
    values.update(
        test_login_email=system["email"],
        test_login_password_hash=password_hash,
        test_login_expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    values.update(overrides)
    return Settings(**values)


def submit(client, email, password="A synthetic test password", **kwargs):
    return client.post("/api/auth/password", json={"email": email, "password": password}, **kwargs)


def test_hash_is_salted_and_verifies_exact_input(password_hash):
    assert password_hash != hash_password("A synthetic test password")
    assert validate_password_hash(password_hash) == password_hash
    assert verify_password("A synthetic test password", password_hash)
    assert not verify_password("A synthetic test password ", password_hash)
    with pytest.raises(ValueError):
        validate_password_hash("plain-text-is-not-a-password-hash")


def test_password_login_cookie_scope_logout_and_expiry(system, password_hash):
    settings = configured(
        system, password_hash, public_url="https://testserver", secure_cookies=True
    )
    with TestClient(create_app(settings), base_url=settings.public_url) as client:
        client.headers["Origin"] = settings.public_url
        assert client.get("/api/auth/providers").json()["password"] is True
        response = submit(client, system["email"].upper())
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert all(value in cookie for value in ("httponly", "secure", "samesite=lax"))
        token = client.cookies["dispatcher_session"]
        assert client.get("/api/auth/me").json()["user_id"] == str(system["owner"].subject_id)
        assert (
            client.get(
                "/api/overview", headers={"X-Tenant-ID": str(system["owner"].tenant_id)}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/overview", headers={"X-Tenant-ID": str(system["other"].tenant_id)}
            ).status_code
            == 403
        )
        with system["db"].auth() as connection:
            expiry = connection.execute(_SQL_SESSION_EXPIRY, (verifier(token),)).fetchone()[
                "expires_at"
            ]
            assert expiry <= settings.test_login_expires_at
        assert client.post("/api/auth/logout").status_code == 204
        client.cookies.set("dispatcher_session", token)
        assert client.get("/api/auth/me").status_code == 401
        client.cookies.clear()
        assert submit(client, system["email"]).status_code == 200
        with system["db"].auth() as connection:
            connection.execute(
                _SQL_EXPIRE_SESSION, (verifier(client.cookies["dispatcher_session"]),)
            )
        assert client.get("/api/auth/me").status_code == 401


def test_invalid_credentials_and_origin_cannot_issue_session(system, password_hash):
    settings = configured(system, password_hash)
    with TestClient(create_app(settings)) as client:
        assert submit(client, system["email"]).status_code == 403
        client.headers["Origin"] = settings.public_url
        for email, password in [
            (system["email"], "wrong"),
            ("another@example.test", "A synthetic test password"),
        ]:
            assert submit(client, email, password).status_code == 401
            assert "dispatcher_session" not in client.cookies
        assert submit(client, system["email"], "x" * 1025).status_code == 422


def test_failed_attempts_commit_and_cannot_bypass_limit_with_other_email(system, password_hash):
    settings = configured(system, password_hash, login_requests_per_window=2)
    with TestClient(create_app(settings), client=(uuid4().hex, 50000)) as client:
        client.headers["Origin"] = settings.public_url
        # The existing fixture consumed one attempt for this identity.
        assert submit(client, system["email"], "wrong").status_code == 401
        assert submit(client, "another@example.test", "wrong").status_code == 429
        assert submit(client, system["email"]).status_code == 429
        assert "dispatcher_session" not in client.cookies


def test_disabled_expired_and_nonexistent_identity_fail_closed(system, password_hash):
    for settings in [
        system["db"].settings,
        configured(
            system, password_hash, test_login_expires_at=datetime.now(UTC) - timedelta(seconds=1)
        ),
    ]:
        with TestClient(create_app(settings)) as client:
            client.headers["Origin"] = settings.public_url
            assert client.get("/api/auth/providers").json()["password"] is False
            assert submit(client, system["email"]).status_code == 503
    settings = configured(system, password_hash, test_login_email=f"{uuid4().hex}@example.test")
    with system["db"].auth() as connection:
        before = connection.execute(_SQL_USER_COUNT).fetchone()["n"]
    with TestClient(create_app(settings)) as client:
        client.headers["Origin"] = settings.public_url
        assert submit(client, settings.test_login_email).status_code == 401
    with system["db"].auth() as connection:
        assert connection.execute(_SQL_USER_COUNT).fetchone()["n"] == before


def test_settings_require_complete_configuration_and_aware_expiry(system, password_hash):
    for fields in [
        dict(test_login_email=system["email"]),
        dict(test_login_expires_at="2030-01-01T00:00:00"),
    ]:
        values = system["db"].settings.model_dump()
        values.update(fields)
        with pytest.raises(ValidationError):
            Settings(**values)
    settings = configured(system, password_hash)
    assert isinstance(settings.test_login_password_hash, SecretStr)
    assert password_hash not in repr(settings)

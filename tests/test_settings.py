"""Startup diagnostics must not expose credentials from environment input."""

import pytest
from dispatcher.settings import Settings
from pydantic import ValidationError


def test_startup_validation_redacts_raw_environment_values():
    with pytest.raises(ValidationError) as caught:
        Settings(
            database_url="postgresql://owner:private-owner-password@database/ledger",
            auth_database_url="postgresql://auth:private-auth-password@database/ledger",
            session_secret="private-session-secret-that-is-long-enough",
            public_url="http://insecure.example.test",
            secure_cookies=True,
        )
    message = str(caught.value)
    assert "requires an HTTPS" in message
    assert "private-" not in message
    assert "input_value" not in message

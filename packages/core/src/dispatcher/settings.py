"""Deployment configuration; secrets are never read from tracked files."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dispatcher.configuration_document import ConfigSource


class Settings(BaseSettings):
    """Load service configuration from DISPATCHER_ environment variables."""

    model_config = SettingsConfigDict(env_prefix="DISPATCHER_", extra="ignore")
    database_url: SecretStr
    auth_database_url: SecretStr
    public_url: str
    session_secret: SecretStr
    secure_cookies: bool = True
    session_seconds: int = 43200
    login_seconds: int = 600
    key_seconds: int = 7776000
    invite_seconds: int = Field(default=172800, gt=0)
    reauth_seconds: int = Field(default=600, gt=0)
    delegation_seconds: int = Field(default=300, gt=0)
    tool_token_seconds: int = Field(default=3600, gt=0, le=86400)
    tool_resource_url: str = ""
    secret_bytes: int = Field(default=32, ge=32)
    request_limit: int = 1000
    page_size: int = 100
    worker_interval: float = 30
    worker_health_file: Path = Path("/tmp/dispatcher-worker-health")
    worker_health_ttl_seconds: float = 120
    heartbeat_grace_seconds: int = 300
    worker_lease_seconds: int = Field(default=120, gt=0)
    schedule_catchup_limit: int = Field(default=100, gt=0)
    snapshot_stale_seconds: int = Field(default=86400, gt=0)
    login_requests_per_window: int = 5
    login_window_seconds: int = 900
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    smtp_starttls: bool = True
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_metadata_url: str = "https://accounts.google.com/.well-known/openid-configuration"
    http_timeout: float = 10
    gateway_url: str = ""
    gateway_master_key: SecretStr = SecretStr("")
    gateway_callback_secret: SecretStr = SecretStr("")
    config_sources: dict[str, ConfigSource] = Field(default_factory=dict)
    config_max_bytes: int = Field(default=65536, gt=0)
    config_poll_seconds: int = Field(default=60, gt=0)
    config_runtime_ttl: int = Field(default=300, gt=0)
    config_clock_skew_seconds: int = Field(default=30, ge=0)
    agentdesk_identity_url: str = ""
    identity_max_bytes: int = Field(default=16384, ge=1024, le=65536)

    @model_validator(mode="after")
    def validate_security(self):
        """Reject unsafe credentials and invalid policy values at startup."""
        if len(self.session_secret.get_secret_value()) < self.secret_bytes:
            raise ValueError("session_secret must contain at least secret_bytes characters")
        if not self.public_url.startswith(("https://", "http://")):
            raise ValueError("public_url must be an absolute HTTP(S) URL")
        if self.secure_cookies and not self.public_url.startswith("https://"):
            raise ValueError("secure_cookies requires an HTTPS public_url")
        for name in ("agentdesk_identity_url", "tool_resource_url"):
            if not getattr(self, name):
                continue
            identity_url = urlsplit(getattr(self, name))
            if (
                identity_url.scheme not in {"http", "https"}
                or not identity_url.hostname
                or identity_url.username
                or identity_url.password
                or identity_url.query
                or identity_url.fragment
            ):
                raise ValueError(f"{name} must be an absolute URL without credentials")
            if self.secure_cookies and identity_url.scheme != "https":
                raise ValueError(f"{name} requires HTTPS in production")
        for name in (
            "session_seconds",
            "login_seconds",
            "key_seconds",
            "request_limit",
            "page_size",
            "worker_interval",
            "worker_health_ttl_seconds",
            "heartbeat_grace_seconds",
            "login_requests_per_window",
            "login_window_seconds",
            "http_timeout",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per service process."""
    return Settings()

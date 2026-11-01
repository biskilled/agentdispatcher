"""Generate private local configuration without committing reusable demo credentials."""

import secrets
from pathlib import Path


def main() -> None:
    """Create .env once; never overwrite a user's deployment configuration."""
    root = Path(__file__).resolve().parents[1]
    destination = root / ".env"
    if destination.exists():
        raise SystemExit(".env already exists; edit it directly instead of replacing secrets")
    values = {}
    for line in (root / ".env.example").read_text().splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    for key in (
        "POSTGRES_PASSWORD",
        "DISPATCHER_APP_DB_PASSWORD",
        "DISPATCHER_AUTH_DB_PASSWORD",
        "DISPATCHER_SESSION_SECRET",
        "LITELLM_MASTER_KEY",
        "DISPATCHER_GATEWAY_DB_PASSWORD",
        "DISPATCHER_GATEWAY_CALLBACK_SECRET",
    ):
        values[key] = secrets.token_urlsafe(48)
    values["LITELLM_MASTER_KEY"] = "sk-" + values["LITELLM_MASTER_KEY"]
    for key, user, password in (
        ("DISPATCHER_DATABASE_URL", "dispatcher_app", "DISPATCHER_APP_DB_PASSWORD"),
        ("DISPATCHER_AUTH_DATABASE_URL", "dispatcher_auth", "DISPATCHER_AUTH_DB_PASSWORD"),
        ("DISPATCHER_MIGRATION_DATABASE_URL", values["POSTGRES_USER"], "POSTGRES_PASSWORD"),
        ("LITELLM_DATABASE_URL", "dispatcher_gateway", "DISPATCHER_GATEWAY_DB_PASSWORD"),
    ):
        values[key] = f"postgresql://{user}:{values[password]}@db:5432/{values['POSTGRES_DB']}"
    values["LITELLM_DATABASE_URL"] += "?schema=litellm"
    # Exclusive create and restrictive mode apply before any secret reaches disk.
    import os

    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    print("Created private .env. Run docker compose up --build -d.")


if __name__ == "__main__":
    main()

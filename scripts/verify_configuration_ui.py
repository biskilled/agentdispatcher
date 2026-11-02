"""Exercise real configuration editing in an isolated browser/API fixture using local PostgreSQL."""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.db import Database
from dispatcher.settings import Settings
from dotenv import load_dotenv

_DOCUMENT = '# Fixture\nllm:\n  model: model-a # retain comment\nprompt: "private fixture"\n'


def serve():
    """Mount the built UI after API routes; fixture configuration is supplied only by the parent."""
    import uvicorn
    from dispatcher.api import create_app
    from fastapi.staticfiles import StaticFiles

    app = create_app()
    app.mount("/", StaticFiles(directory="dist/ui", html=True), name="fixture-ui")
    uvicorn.run(
        app,
        host=os.environ["FIXTURE_HOST"],
        port=int(os.environ["FIXTURE_PORT"]),
        access_log=False,
        log_level="warning",
    )


def main():
    """Create disposable source files and scoped credentials; revoke credentials on every exit."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    settings = Settings()
    auth = AuthService(Database(settings))
    email = f"configuration-ui-{uuid4().hex}@example.test"
    owner = create_tenant(auth.db, "Configuration browser fixture", email)
    session = auth.consume_login(auth.request_login(email, email))
    key = auth.issue_key(owner, "configuration-fixture", "config-fixture", "test")
    try:
        with tempfile.TemporaryDirectory(prefix="dispatcher-config-ui-") as directory:
            sources = {}
            for viewport in ("desktop", "mobile"):
                path = Path(directory) / f"{viewport}.yaml"
                path.write_text(_DOCUMENT)
                sources[viewport] = {
                    "tenant_id": str(owner.tenant_id),
                    "app": "config-fixture",
                    "environment": "test",
                    "kind": "file",
                    "root": directory,
                    "path": path.name,
                    "writable": True,
                    "fields": {"llm.model": {"kind": "model", "models": ["model-a", "model-b"]}},
                }
            with socket.socket() as listener:
                listener.bind((args.host, 0))
                port = listener.getsockname()[1]
            base = f"http://{args.host}:{port}"
            environment = dict(
                os.environ,
                DISPATCHER_CONFIG_SOURCES=json.dumps(sources),
                DISPATCHER_PUBLIC_URL=base,
                DISPATCHER_SECURE_COOKIES="false",
                DISPATCHER_TEST_CONFIG_UI_URL=base,
                DISPATCHER_TEST_SESSION=session,
                DISPATCHER_TEST_TENANT=str(owner.tenant_id),
                DISPATCHER_TEST_CONFIG_KEY=key["secret"],
                FIXTURE_HOST=args.host,
                FIXTURE_PORT=str(port),
            )
            process = subprocess.Popen([sys.executable, __file__, "--serve"], env=environment)
            try:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        response = httpx.get(base + "/health/ready")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass  # Startup is bounded and fails explicitly below.
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Configuration fixture API failed to start")
                    time.sleep(0.1)
                subprocess.run(
                    ["npm", "run", "test:ui", "--", "tests/ui/configuration.spec.ts"],
                    env=environment,
                    check=True,
                )
                for viewport in sources:
                    restored = (Path(directory) / f"{viewport}.yaml").read_text()
                    assert 'model: "model-a" # retain comment' in restored
                    assert 'prompt: "private fixture"' in restored
            finally:
                process.terminate()
                process.wait(timeout=10)
    finally:
        auth.logout(session)
        auth.revoke_key(owner, key["id"])
    print("Connected YAML browser editing, failed activation and rollback verified at both widths.")


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
    else:
        main()

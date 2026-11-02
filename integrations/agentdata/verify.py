"""Verify actual AgentData source against disposable tenant analytics and a synthetic gateway."""

import argparse
import json
import os
import secrets
import subprocess
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from dispatcher.analytics import provision, revoke
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.contracts import UsageEvent
from dispatcher.db import Database
from dispatcher.gateway import Gateway
from dispatcher.ledger import Ledger
from dispatcher.migrations import migrate
from dispatcher.observations import Observations
from dispatcher.settings import get_settings
from dotenv import load_dotenv
from prepare_patch import prepare
from psycopg.conninfo import conninfo_to_dict
from pydantic import SecretStr


def analytics_url(dsn, role, password):
    """Build a fixture-only SQLAlchemy URL without logging its credential."""
    parts = conninfo_to_dict(dsn)
    return (
        f"postgresql+psycopg2://{quote(role)}:{quote(password)}@"
        f"{parts['host']}:{parts['port']}/{quote(parts['dbname'])}"
    )


def main():
    """Require explicit app/interpreter paths and a disposable owner connection environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--agentdata", required=True, type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--database-env", default="TEST_DATABASE_URL")
    parser.add_argument(
        "--applied", action="store_true", help="Verify the already patched checkout directly"
    )
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    dsn = os.environ[args.database_env]
    migrate(dsn)
    settings = get_settings()
    settings.gateway_url = "https://synthetic-gateway.example.test"
    settings.gateway_master_key = SecretStr("synthetic-master-key")
    db = Database(settings)
    auth, ledger = AuthService(db), Ledger(db)
    gateway = Gateway(
        db,
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"key": json.loads(request.content)["key"]})
        ),
    )
    bindings, records, virtuals, tenants = {}, [], {}, []
    environment = {"FIXTURE_DISPATCHER_ENDPOINT": os.environ["DISPATCHER_DEMO_ENDPOINT"]}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            """Keep synthetic request contents and headers out of logs."""

        def do_POST(self):
            """Model the authenticated callback boundary without making paid provider calls."""
            service = virtuals.get(self.headers.get("Authorization", ""))
            if service is None:
                self.send_error(401)
                return
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            context = body["metadata"]["dispatcher_context"]
            assert context["feature"] == "fixture_summary"
            assert len(context["config_version"]) == 64
            assert "Synthetic private" not in json.dumps(context)
            principal = gateway.principal(service, body["model"])
            ledger.ingest(
                principal,
                [
                    UsageEvent(
                        event_id=uuid4(),
                        attempt_id=uuid4(),
                        operation_id=UUID(context.pop("operation_id")),
                        occurred_at=datetime.now(UTC),
                        app=principal.app,
                        environment=principal.environment,
                        source="litellm",
                        provider="synthetic",
                        operation="completion",
                        resource_kind="llm",
                        model=body["model"],
                        status="success",
                        status_code=200,
                        duration_ms=1,
                        input_tokens=7,
                        output_tokens=3,
                        reported_cost="0.013",
                        reported_currency="USD",
                        **context,
                    )
                ],
            )
            response = json.dumps(
                {
                    "choices": [{"message": {"content": "Synthetic private answer"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment["FIXTURE_GATEWAY_ENDPOINT"] = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        for index in range(2):
            owner = create_tenant(
                db, "Synthetic AgentData integration", f"data-{uuid4()}@example.test"
            )
            tenants.append(owner)
            key = auth.issue_key(owner, "AgentData fixture", "AgentData", "test")
            virtual = gateway.issue(
                owner, "AgentData fixture", "AgentData", "test", ["fixture-model"]
            )
            virtuals["Bearer " + virtual["secret"]] = virtual["id"]
            environment[f"FIXTURE_SDK_{index}"] = key["secret"]
            environment[f"FIXTURE_GATEWAY_{index}"] = virtual["secret"]
            bindings[str(index)] = {
                "endpoint_env": "FIXTURE_DISPATCHER_ENDPOINT",
                "key_env": f"FIXTURE_SDK_{index}",
                "app": "AgentData",
                "environment": "test",
                "gateway_endpoint_env": "FIXTURE_GATEWAY_ENDPOINT",
                "gateway_key_env": f"FIXTURE_GATEWAY_{index}",
            }
            ledger.ingest(
                auth.service(key["secret"]),
                [
                    UsageEvent(
                        event_id=uuid4(),
                        attempt_id=uuid4(),
                        operation_id=uuid4(),
                        occurred_at=datetime.now(UTC),
                        app="AgentData",
                        environment="test",
                        source="fixture",
                        provider="synthetic",
                        operation="fixture",
                        resource_kind="llm",
                        status="success",
                        input_tokens=7 + index,
                        reported_cost=str(index + 1),
                        reported_currency="USD",
                    )
                ],
            )
            password = secrets.token_urlsafe(32)
            role = provision(dsn, owner.tenant_id, password)
            overview = ledger.overview(owner)
            records.append(
                {
                    "scope": index,
                    "url": analytics_url(dsn, role, password),
                    "attempts": overview["counts"]["attempts"],
                    "tokens": 7 + index,
                    "totals": overview["totals"],
                    "providers": {"synthetic": 1},
                    "key_id": str(key["id"]),
                    "gateway_id": str(virtual["id"]),
                }
            )
        for index, record in enumerate(records):
            record["other"] = str(tenants[1 - index].tenant_id)
        environment["AGENTDATA_DISPATCHER_BINDINGS"] = json.dumps(bindings)
        with TemporaryDirectory(prefix="agentdata-dispatcher-") as overlay:
            core = Path(overlay) / "core"
            core.mkdir()
            (core / "__init__.py").write_text(
                "from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n"
            )
            if not args.applied:
                for name, (_, updated) in prepare(args.agentdata).items():
                    (core / Path(name).name).write_text(updated)
            paths = [
                overlay,
                str(args.agentdata / "backend"),
                str(Path("packages/sdk/src").resolve()),
            ]
            child_env = dict(os.environ, PYTHONPATH=os.pathsep.join(paths))
            subprocess.run(
                [args.python, str(Path(__file__).with_name("exercise.py").resolve())],
                input=json.dumps({"tenants": records, "environment": environment}, default=str),
                env=child_env,
                text=True,
                check=True,
                timeout=60,
            )
        for owner in tenants:
            rows = ledger.events(owner)
            assert len(rows) == 2
            routed = next(row for row in rows if row["payload"]["source"] == "litellm")
            assert routed["payload"]["feature"] == "fixture_summary"
            assert len(routed["payload"]["config_version"]) == 64
            assert "Synthetic private" not in str(rows)
            coverage = Observations(db).coverage(owner)
            assert sum(row["matched"] for row in coverage["references"]) == 1, coverage
        print(
            "Two AgentData tenants: analytics parity and one correlated gateway charge each."
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        for owner, record in zip(tenants, records, strict=False):
            auth.revoke_key(owner, UUID(record["key_id"]))
            auth.revoke_key(owner, UUID(record["gateway_id"]))
            revoke(dsn, owner.tenant_id)


if __name__ == "__main__":
    main()

"""Verify real AgentTrade code → SDK → HTTP intake → PostgreSQL → dashboard totals."""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.contracts import ApiPlan
from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.settings import get_settings
from dotenv import load_dotenv


def main():
    """Use explicit local paths and a configured disposable Dispatcher installation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--agenttrade", required=True, type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument(
        "--mcp-python", required=True, help="Interpreter with official MCP SDK and monitoring SDK"
    )
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    settings = get_settings()
    db = Database(settings)
    auth, ledger = AuthService(db), Ledger(db)
    endpoint = os.environ["DISPATCHER_DEMO_ENDPOINT"]
    environment = {
        "FIXTURE_DISPATCHER_ENDPOINT": endpoint,
        "FIXTURE_CONFIG_VERSION": "synthetic-configuration-version",
    }
    bindings, tenants = {}, []
    for index in range(2):
        identity = uuid4().hex
        email = f"trade-{identity}@example.test"
        owner = create_tenant(db, "Synthetic AgentTrade integration", email)
        key = auth.issue_key(owner, "Synthetic AgentTrade integration", "AgentTrade", "fixture")
        environment[f"FIXTURE_KEY_{index}"] = key["secret"]
        bindings[identity] = {
            "endpoint_env": "FIXTURE_DISPATCHER_ENDPOINT",
            "key_env": f"FIXTURE_KEY_{index}",
            "app": "AgentTrade",
            "environment": "fixture",
            "context": {"project": "AgentTrade", "work_item": "TA10012"},
            "config_version_env": "FIXTURE_CONFIG_VERSION",
            "providers": {
                "fixture-llm": {"resource_kind": "llm", "api_id": "fixture-llm"},
                "fixture-market": {"api_id": "fixture-market"},
            },
        }
        for api_id, pricing in [
            (
                "fixture-llm",
                {
                    "pricing": "per_token",
                    "input_token_price": "0.001",
                    "output_token_price": "0.002",
                },
            ),
            ("fixture-market", {"pricing": "per_unit", "unit_price": "0.01"}),
            (
                "fixture-tool",
                {"pricing": "per_unit", "unit_price": "0.02", "charge_outcomes": ["success"]},
            ),
        ]:
            ledger.add_plan(
                owner,
                ApiPlan(
                    api_id=api_id,
                    name="Synthetic integration tariff",
                    effective_at=datetime.now(UTC) - timedelta(days=1),
                    source_note="Synthetic; no vendor prices",
                    **pricing,
                ),
            )
        tenants.append((owner, email, key["id"]))
    environment["AGENTTRADE_DISPATCHER_BINDINGS"] = json.dumps(bindings)
    script = Path(__file__).with_name("exercise_scheduler.py").resolve()
    child_environment = dict(os.environ, PYTHONPATH=str(args.agenttrade / "services/advisor"))
    try:
        subprocess.run(
            [args.python, str(script)],
            input=json.dumps(
                {
                    "environment": environment,
                    "organisations": list(bindings),
                    "mcp_python": args.mcp_python,
                }
            ),
            text=True,
            env=child_environment,
            check=True,
            timeout=60,
        )
        for owner, email, _ in tenants:
            overview = ledger.overview(owner)
            assert overview["counts"]["attempts"] == 8
            assert overview["counts"]["failures"] == 2
            assert overview["counts"]["input_tokens"] == 28
            assert sum(row["cost"] or Decimal(0) for row in overview["totals"]) == Decimal("0.082")
            rows = ledger.events(owner)
            assert all(
                row["payload"]["config_version"] == "synthetic-configuration-version"
                for row in rows
            )
            assert "Synthetic private" not in str(rows)
            runs = ledger.jobs(owner)
            assert len({row["trace_id"] for row in runs}) == 2
            completed = next(row for row in runs if row["state"] == "completed")
            children = [row for row in rows if row["payload"]["trace_id"] == completed["trace_id"]]
            assert len(children) == 7
            assert {str(row["job_run_id"]) for row in children} == {str(completed["run_id"])}
            assert len([row for row in children if row["resource_kind"] == "tool"]) == 1
            assert {row["state"] for row in ledger.jobs(owner)} == {"completed", "failed"}
            token = auth.request_login(email, "agenttrade-synthetic-verification")
            session = auth.consume_login(token)
            with httpx.Client(
                base_url=endpoint,
                headers={"X-Tenant-ID": str(owner.tenant_id), "Origin": settings.public_url},
                cookies={"dispatcher_session": session},
            ) as client:
                try:
                    response = client.get("/api/overview")
                    response.raise_for_status()
                    assert response.json()["counts"]["attempts"] == 8
                    assert sum(
                        Decimal(row["cost"] or "0") for row in response.json()["totals"]
                    ) == Decimal("0.082")
                finally:
                    client.post("/api/auth/logout").raise_for_status()
        print(
            "Verified two tenant ledgers: 8 attempts, 28 input tokens and USD 0.082 each; "
            "dashboard matches."
        )
    finally:
        for owner, _, key_id in tenants:
            auth.revoke_key(owner, key_id)


if __name__ == "__main__":
    main()

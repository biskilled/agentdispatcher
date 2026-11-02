"""Verify the pinned collector forwards authenticated metadata into the real ledger."""

import argparse
import os
import secrets
import time
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.contracts import Principal
from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.settings import get_settings
from dispatcher.source_health import SourceHealth
from dotenv import dotenv_values


def prepare(path):
    """Create a private fixture environment; never print bearer credentials."""
    db = Database(get_settings())
    owner = create_tenant(db, "Collector fixture", f"collector-{uuid4().hex}@example.test")
    key = AuthService(db).issue_key(owner, "Collector fixture", "collector-fixture", "test")
    values = {
        "DISPATCHER_COLLECTOR_TOKEN": secrets.token_urlsafe(32),
        "DISPATCHER_OTLP_SDK_KEY": key["secret"],
        "DISPATCHER_FIXTURE_KEY_ID": str(key["id"]),
        "DISPATCHER_FIXTURE_TENANT": str(owner.tenant_id),
        "DISPATCHER_FIXTURE_OWNER": str(owner.subject_id),
    }
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as target:
        target.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")


def attribute(key, value):
    """Encode only synthetic scalar data in standard OTLP JSON."""
    return {"key": key, "value": {"boolValue" if type(value) is bool else "stringValue": value}}


def body():
    """A tool and its two nested LLM calls have distinct, explicitly supplied costs."""
    start = time.time_ns()
    trace_id = uuid4().hex
    spans = []
    for kind, amount in (("tool", "0.02"), ("llm", "0.04"), ("llm", "0.06")):
        values = {
            "dispatcher.provider": "synthetic-tool" if kind == "tool" else "synthetic-llm",
            "dispatcher.cost": amount,
            "dispatcher.currency": "USD",
            "gen_ai.input.messages": "private fixture prompt",
        }
        if kind == "tool":
            values.update(
                {
                    "dispatcher.billable_attempt": True,
                    "dispatcher.resource_kind": "tool",
                    "dispatcher.operation": "lookup",
                }
            )
        else:
            values["gen_ai.operation.name"] = "chat"
        spans.append(
            {
                "traceId": trace_id,
                "spanId": uuid4().hex[:16],
                "name": "private span name",
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(start + 1_000_000),
                "attributes": [attribute(key, value) for key, value in values.items()],
            }
        )
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        attribute("service.name", "collector-fixture"),
                        attribute("deployment.environment.name", "test"),
                    ]
                },
                "scopeSpans": [{"spans": spans}],
            }
        ]
    }


def verify(path):
    """Check inbound auth, asynchronous export, deduplication, privacy and backend revocation."""
    settings = get_settings()
    db = Database(settings)
    state = dotenv_values(path)
    owner = Principal(
        tenant_id=UUID(state["DISPATCHER_FIXTURE_TENANT"]),
        subject_id=UUID(state["DISPATCHER_FIXTURE_OWNER"]),
        role="owner",
    )
    auth, ledger = AuthService(db), Ledger(db)
    endpoint = os.environ["DISPATCHER_COLLECTOR_INTERNAL_URL"]
    key_id = UUID(state["DISPATCHER_FIXTURE_KEY_ID"])
    try:
        with httpx.Client(timeout=10) as client:
            deadline = time.monotonic() + 30
            while True:
                try:
                    if client.post(endpoint, json={}).status_code in {401, 403}:
                        break
                except httpx.TransportError:
                    pass  # Container readiness has a bounded deadline below.
                if time.monotonic() > deadline:
                    raise RuntimeError("Collector did not establish its authenticated receiver")
                time.sleep(0.2)
            payload = body()
            for _ in range(2):
                client.post(
                    endpoint,
                    json=payload,
                    headers={
                        "Authorization": "Bearer " + state["DISPATCHER_COLLECTOR_TOKEN"],
                    },
                ).raise_for_status()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                health = SourceHealth(db).list(owner)
                if health and health[0]["accepted_exports"] >= 6:
                    break
                time.sleep(0.2)
            rows = ledger.events(owner)
            assert health and health[0]["accepted_exports"] >= 6
            assert health[0]["rejected_exports"] == 0
            assert len(rows) == 3, f"Expected three unique attempts, got {len(rows)}"
            assert sum(row["cost"] for row in rows) == Decimal("0.12")
            assert "private" not in str(rows)
            assert len({row["payload"]["trace_id"] for row in rows}) == 1
            upstream = os.environ["DISPATCHER_API_INTERNAL_URL"] + "/api/otlp/v1/traces"
            authorization = {"Authorization": "Bearer " + state["DISPATCHER_OTLP_SDK_KEY"]}
            payload["resourceSpans"][0]["resource"]["attributes"].append(
                attribute("tenant.id", str(uuid4()))
            )
            assert client.post(upstream, json=payload, headers=authorization).status_code == 403
            auth.revoke_key(owner, key_id)
            assert client.post(upstream, json=body(), headers=authorization).status_code == 401
    finally:
        auth.revoke_key(owner, key_id)
    print(
        "Real collector: authenticated OTLP, nested tool/LLM totals, replay, privacy "
        "and key revocation verified."
    )


def main():
    """Prepare private fixture configuration or verify its running collector."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--state", type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.prepare)
    elif args.state:
        verify(args.state)
    else:
        parser.error("Supply --prepare or --state")


if __name__ == "__main__":
    main()

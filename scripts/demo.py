"""Seed synthetic mixed-workload telemetry through the real SDK and HTTP intake."""

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from agentdispatcher_sdk import Monitor
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.contracts import ApiPlan, Principal
from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.settings import get_settings

_SQL_DEMO_OWNER = """
SELECT m.tenant_id,m.user_id FROM mng_memberships m
JOIN mng_identities i ON i.user_id=m.user_id
JOIN mng_tenants t ON t.id=m.tenant_id
WHERE i.issuer='email' AND i.subject=%s AND t.name=%s AND m.role='owner'
ORDER BY t.created_at LIMIT 1
"""


def seed(db: Database, endpoint: str, owner: Principal) -> None:
    """Seed a new synthetic workspace once; never contact a provider or spend money."""
    ledger, auth = Ledger(db), AuthService(db)
    if ledger.overview(owner)["counts"]["attempts"]:
        return
    ledger.add_plan(
        owner,
        ApiPlan(
            api_id="fixture-market",
            name="Synthetic market data",
            effective_at=datetime.now(UTC) - timedelta(days=1),
            pricing="per_unit",
            unit_price=Decimal("0.0025"),
            source_note="Synthetic fixture price; not a vendor price",
        ),
    )
    for app, job in (
        ("AgentTrade", "Market scan"),
        ("Research", "Daily brief"),
        ("AgentData", "Portfolio summary"),
    ):
        key = auth.issue_key(owner, "Synthetic demo", app, "demo")
        monitor = Monitor(endpoint, key["secret"], app, "demo")
        with monitor.job(job):
            for index in range(3):
                monitor.record(
                    provider="Synthetic market API",
                    operation="price.snapshot",
                    resource_kind="api",
                    status="success",
                    status_code=200,
                    duration_ms=12 + index,
                    api_id="fixture-market",
                    units="3",
                )
                monitor.record(
                    provider="Synthetic LLM",
                    operation="analysis",
                    resource_kind="llm",
                    status="error" if index == 2 else "success",
                    duration_ms=450 + index,
                    model="fixture-small",
                    input_tokens=250,
                    output_tokens=90,
                )
        if not monitor.close() or monitor.failed or monitor.dropped:
            raise RuntimeError("Demo exporter failed; verify API connection and logs")
    ledger.tick()


def main() -> None:
    """Print one short-lived local demo sign-in link, never a reusable password."""
    settings = get_settings()
    db = Database(settings)
    email = os.environ.get("DISPATCHER_DEMO_EMAIL", "demo@example.test")
    name = "Synthetic demo workspace"
    with db.auth() as connection:
        row = connection.execute(_SQL_DEMO_OWNER, (email, name)).fetchone()
    owner = (
        Principal(tenant_id=row["tenant_id"], subject_id=row["user_id"], role="owner")
        if row
        else create_tenant(db, name, email)
    )
    seed(db, os.environ["DISPATCHER_DEMO_ENDPOINT"], owner)
    token = AuthService(db).request_login(email, "local-demo-operator")
    if token is None:
        raise SystemExit("Demo sign-in is rate-limited. Wait for the configured login window.")
    print(
        json.dumps(
            {
                "tenant_id": str(owner.tenant_id),
                "synthetic": True,
                "sign_in": settings.public_url.rstrip("/") + "/#signin=" + token,
            }
        )
    )


if __name__ == "__main__":
    main()

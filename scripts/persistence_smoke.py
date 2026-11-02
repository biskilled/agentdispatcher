"""Check two synthetic ledgers through a container restart using ordinary runtime RLS."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.contracts import Principal, UsageEvent
from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.settings import get_settings


def fingerprint(ledger, owner):
    """Compare stored attempts and their exact prices, without putting payloads in logs."""
    rows = ledger.events(owner)
    return hashlib.sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()


def main():
    """Capture only fixture IDs/hashes; verify them after independently restarting services."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "verify"))
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    db = Database(get_settings())
    ledger, auth = Ledger(db), AuthService(db)
    if args.action == "capture":
        state = []
        for cost in ("0.123456789", "0.987654321"):
            owner = create_tenant(
                db, "Synthetic restart fixture", f"restart-{uuid4()}@example.test"
            )
            key = auth.issue_key(owner, "Restart fixture", "restart-fixture", "test")
            try:
                ledger.ingest(
                    auth.service(key["secret"]),
                    [
                        UsageEvent(
                        event_id=uuid4(),
                        attempt_id=uuid4(),
                        operation_id=uuid4(),
                        occurred_at=datetime.now(UTC),
                        status="success",
                            app="restart-fixture",
                            environment="test",
                            source="restart-fixture",
                            resource_kind="api",
                            provider="synthetic",
                            operation="restart",
                            reported_cost=cost,
                            reported_currency="USD",
                        )
                    ],
                )
                state.append(
                    {
                        "tenant": str(owner.tenant_id),
                        "user": str(owner.subject_id),
                        "digest": fingerprint(ledger, owner),
                    }
                )
            finally:
                auth.revoke_key(owner, key["id"])
        with args.state.open("x") as handle:
            args.state.chmod(0o600)
            json.dump(state, handle)
    else:
        for item in json.loads(args.state.read_text()):
            owner = Principal(
                tenant_id=UUID(item["tenant"]), subject_id=UUID(item["user"]), role="owner"
            )
            assert fingerprint(ledger, owner) == item["digest"], "Restart changed fixture evidence"
            assert len(ledger.events(owner)) == 1, "Restart changed tenant isolation"
        assert db.ready(), "Application schema is not ready after restart"
    print(f"Synthetic persistence {args.action} passed for two tenants.")


if __name__ == "__main__":
    main()

"""Local operator commands; never exposed as unauthenticated web setup endpoints."""

import argparse
import json
import os
from uuid import UUID

from dispatcher.bootstrap import create_tenant
from dispatcher.db import Database
from dispatcher.settings import get_settings


def main() -> None:
    """Provision a first owner or execute a single worker health tick."""
    parser = argparse.ArgumentParser(description="AgentDispatcher operator commands")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("create-tenant")
    bootstrap.add_argument("--name", required=True)
    bootstrap.add_argument("--email", required=True)
    commands.add_parser("tick")
    analytics = commands.add_parser("analytics-access")
    analytics.add_argument("--tenant", type=UUID, required=True)
    analytics.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    if args.command == "analytics-access":
        from dispatcher.analytics import provision, revoke

        dsn = os.environ["DISPATCHER_MIGRATION_DATABASE_URL"]
        if args.revoke:
            revoke(dsn, args.tenant)
            print(json.dumps({"revoked": str(args.tenant)}))
        else:
            role = provision(dsn, args.tenant, os.environ["DISPATCHER_ANALYTICS_PASSWORD"])
            print(json.dumps({"role": role, "tenant_id": str(args.tenant)}))
        return
    db = Database(get_settings())
    if args.command == "create-tenant":
        principal = create_tenant(db, args.name, args.email)
        print(
            json.dumps(
                {"tenant_id": str(principal.tenant_id), "user_id": str(principal.subject_id)}
            )
        )
    else:
        from dispatcher.ledger import Ledger

        print(json.dumps({"tenants": Ledger(db).tick()}))


if __name__ == "__main__":
    main()

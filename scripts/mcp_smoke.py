"""Verify the separately deployed MCP service against real API authorization and PostgreSQL."""

import os
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.contracts import UsageEvent
from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.settings import get_settings
from dispatcher.tool_access import ToolAccess


def wait_ready(client, endpoint, headers):
    """Wait for the unauthenticated HTTP boundary before issuing fixture credentials."""
    deadline = time.monotonic() + float(os.environ.get("DISPATCHER_MCP_STARTUP_TIMEOUT", "60"))
    while time.monotonic() < deadline:
        try:
            if client.get(endpoint, headers=headers).status_code == 401:
                return
        except httpx.TransportError:
            pass  # Expected during container startup; the bounded deadline fails the check.
        time.sleep(1)
    raise RuntimeError("MCP service did not become ready")


def main():
    """Use synthetic tenants and short-lived grants; never print reusable credentials."""
    settings = get_settings()
    db = Database(settings)
    auth, ledger = AuthService(db), Ledger(db)
    access = ToolAccess(auth)
    public = urlsplit(settings.tool_resource_url)
    endpoint = os.environ["DISPATCHER_MCP_INTERNAL_URL"]
    headers = {
        "Host": public.netloc,
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    with httpx.Client(timeout=30) as client:
        wait_ready(client, endpoint, headers)
        for index in range(2):
            email = f"mcp-{uuid4().hex}@example.test"
            owner = create_tenant(db, f"MCP fixture {index}", email)
            session = auth.consume_login(auth.request_login(email, email))
            grant = access.issue(session, owner.tenant_id, False)
            key = auth.issue_key(owner, "fixture", "mcp-fixture", "test")
            try:
                ledger.ingest(
                    auth.service(key["secret"]),
                    [
                        UsageEvent(
                            event_id=uuid4(),
                            attempt_id=uuid4(),
                            operation_id=uuid4(),
                            occurred_at=datetime.now(UTC),
                            app="mcp-fixture",
                            environment="test",
                            resource_kind="api",
                            source="fixture",
                            provider="fixture",
                            operation="read",
                            status="success",
                            duration_ms=1,
                        )
                    ],
                )
                request_headers = {**headers, "Authorization": "Bearer " + grant["secret"]}
                initialized = client.post(
                    endpoint,
                    headers=request_headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-11-25",
                            "capabilities": {},
                            "clientInfo": {"name": "dispatcher-fixture", "version": "1"},
                        },
                    },
                )
                initialized.raise_for_status()
                assert "result" in initialized.json()
                body = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "get_usage", "arguments": {}},
                }
                read = client.post(endpoint, headers=request_headers, json=body)
                read.raise_for_status()
                result = read.json()["result"]
                assert not result.get("isError")
                assert result["structuredContent"]["counts"]["attempts"] == 1
                foreign = grant["secret"].replace(str(owner.tenant_id), str(uuid4()), 1)
                assert (
                    client.post(
                        endpoint,
                        headers={**headers, "Authorization": "Bearer " + foreign},
                        json=body,
                    ).status_code
                    == 401
                )
                auth.logout(session)
                assert client.post(endpoint, headers=request_headers, json=body).status_code == 401
            finally:
                auth.logout(session)
                auth.revoke_key(owner, key["id"])
    print("Real MCP service: isolated totals, credential tampering and immediate logout verified.")


if __name__ == "__main__":
    main()

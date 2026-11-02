"""Tool credentials stay separate from service keys and cease working with their human session."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from dispatcher import tool_access
from dispatcher.auth import verifier
from dispatcher.membership import MembershipService
from test_access import invite_user
from test_integration import event, ingest

_SQL_STORED = "SELECT token_hash FROM mng_tool_tokens WHERE id=%s"


def test_tool_reads_scope_expiry_revocation_and_logout(system):
    client = system["client"]
    issued = client.post("/api/tools/access", json={}).json()
    headers = {"Authorization": "Bearer " + issued["secret"]}
    with system["db"].auth() as connection:
        assert connection.execute(_SQL_STORED, (issued["id"],)).fetchone()[
            "token_hash"
        ] == verifier(issued["secret"])
    assert issued["secret"] not in str(client.get("/api/tools/access").json())
    assert ingest(system, [event(session_id="session-a")]).status_code == 202
    assert client.get("/api/tools/usage", headers=headers).json()["counts"]["attempts"] == 1
    assert (
        client.get("/api/tools/sessions/session-a", headers=headers).json()["counts"]["attempts"]
        == 1
    )
    assert client.get("/api/tools/me", headers=headers).json()["resource"].endswith("/api/tools")
    assert (
        client.get(
            "/api/tools/usage", headers={**headers, "X-Tenant-ID": str(system["other"].tenant_id)}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/tools/usage", headers={"Authorization": "Bearer " + system["key"]["secret"]}
        ).status_code
        == 401
    )
    assert (
        client.post("/api/ingest", json={"events": [event()]}, headers=headers).status_code == 401
    )
    assert client.delete("/api/tools/access/" + issued["id"]).status_code == 204
    assert client.get("/api/tools/usage", headers=headers).status_code == 401
    issued = client.post("/api/tools/access", json={}).json()
    headers = {"Authorization": "Bearer " + issued["secret"]}
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/tools/usage", headers=headers).status_code == 401


def test_tool_policy_writes_require_explicit_consent_and_live_admin_role(system):
    client = system["client"]
    session, user, _ = invite_user(system, "admin")
    client.cookies.set("dispatcher_session", session)
    body = {
        "config": {
            "id": "tool-policy",
            "app": "trader",
            "environment": "test",
            "allowed_models": ["configured-model"],
        },
        "revision": 0,
    }
    readonly = client.post("/api/tools/access", json={}).json()
    assert (
        client.put(
            "/api/tools/policy",
            json=body,
            headers={"Authorization": "Bearer " + readonly["secret"]},
        ).status_code
        == 403
    )
    writer = client.post("/api/tools/access", json={"can_write_policy": True}).json()
    headers = {"Authorization": "Bearer " + writer["secret"]}
    assert client.put("/api/tools/policy", json=body, headers=headers).status_code == 200
    assert client.put("/api/tools/policy", json=body, headers=headers).status_code == 409
    assert client.get("/api/policies/tool-policy/history").json()[0]["action"] == "tool.updated"
    MembershipService(system["auth"]).update(system["owner"], user["user_id"], "member", [])
    assert (
        client.put("/api/tools/policy", json={**body, "revision": 1}, headers=headers).status_code
        == 403
    )
    assert client.post("/api/tools/access", json={"can_write_policy": True}).status_code == 403
    assert client.get("/api/tools/experiments", headers=headers).status_code == 403
    MembershipService(system["auth"]).update(system["owner"], user["user_id"], None, [])
    assert client.get("/api/tools/usage", headers=headers).status_code == 401


def test_expired_tool_credential_is_rejected(system, monkeypatch):
    monkeypatch.setattr(
        tool_access,
        "datetime",
        SimpleNamespace(now=lambda zone: datetime.now(zone) - timedelta(days=2)),
    )
    issued = system["client"].post("/api/tools/access", json={}).json()
    assert (
        system["client"]
        .get(
            "/api/tools/me",
            headers={
                "Authorization": "Bearer " + issued["secret"],
            },
        )
        .status_code
        == 401
    )

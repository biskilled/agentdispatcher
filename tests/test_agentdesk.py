"""Live identity introspection cannot bypass explicit tenant and local membership grants."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from agentdispatcher_sdk import Monitor
from dispatcher.membership import MembershipService
from test_access import invite_user
from test_integration import event, ingest


@pytest.fixture
def remote(system, monkeypatch):
    """Inject only the remote HTTP boundary; all local authorization uses real PostgreSQL."""
    adapter = system["client"].app.state.agentdesk
    monkeypatch.setattr(
        adapter.settings, "agentdesk_identity_url", "https://identity.test/auth/dispatcher-identity"
    )
    identity = {
        "subject": str(uuid4()),
        "client_id": str(uuid4()),
        "role": "admin",
        "active": True,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    state = {"identity": identity, "status": 200, "calls": 0}

    def respond(request):
        state["calls"] += 1
        if request.headers["Authorization"] != "Bearer human-test-token":
            return httpx.Response(401)
        return httpx.Response(state["status"], json=state["identity"])

    adapter.transport = httpx.MockTransport(respond)
    return state


def connect(system):
    """Explicitly bind and link as the already authenticated local owner."""
    for action in ("bind", "link"):
        result = system["client"].post(
            f"/api/agentdesk/{action}", json={"token": "human-test-token"}
        )
        assert result.status_code == 204, result.text


def test_agentdesk_identity_scope_and_revocation(system, remote):
    client = system["client"]
    headers = {"Authorization": "Bearer human-test-token"}
    path = "/api/agentdesk/usage"
    assert client.get(path, headers=headers).status_code == 403
    connect(system)
    assert ingest(system, [event(session_id="session-a", work_item="TA1")]).status_code == 202
    assert client.get(path, headers=headers).json()["counts"]["attempts"] == 1
    assert (
        client.get("/api/agentdesk/sessions/session-a", headers=headers).json()["groups"][0][
            "label"
        ]
        == "TA1"
    )
    assert (
        client.get(
            path, headers={**headers, "X-Tenant-ID": str(system["other"].tenant_id)}
        ).status_code
        == 403
    )
    assert (
        client.get(path, headers={"Authorization": "Bearer " + system["key"]["secret"]}).status_code
        == 401
    )
    original = remote["identity"]["client_id"]
    remote["identity"]["client_id"] = str(uuid4())
    assert client.get(path, headers=headers).status_code == 403
    remote["identity"]["client_id"] = original
    remote["status"] = 403
    assert client.get(path, headers=headers).status_code == 401
    remote["status"] = 503
    assert client.get(path, headers=headers).status_code == 503
    remote["status"] = 200
    assert client.delete("/api/agentdesk/link").status_code == 204
    assert client.get(path, headers=headers).status_code == 403
    assert remote["calls"] >= 8


def test_agentdesk_link_cannot_merge_or_escalate(system, remote):
    connect(system)
    client, auth = system["client"], system["auth"]
    owner_session = client.cookies.get("dispatcher_session")
    session, user, _ = invite_user(system, "viewer")
    client.cookies.set("dispatcher_session", session)
    body = {"token": "human-test-token"}
    assert client.post("/api/agentdesk/bind", json=body).status_code == 403
    assert client.post("/api/agentdesk/link", json=body).status_code == 409
    remote["identity"]["subject"] = str(uuid4())
    assert client.post("/api/agentdesk/link", json=body).status_code == 204
    headers = {"Authorization": "Bearer human-test-token"}
    assert client.get("/api/agentdesk/usage", headers=headers).status_code == 403
    MembershipService(auth).update(system["owner"], user["user_id"], "viewer", ["trader"])
    assert ingest(system, [event()]).status_code == 202
    assert client.get("/api/agentdesk/usage", headers=headers).json()["counts"]["attempts"] == 1
    MembershipService(auth).update(system["owner"], user["user_id"], None, [])
    assert client.get("/api/agentdesk/usage", headers=headers).status_code == 403
    client.cookies.set("dispatcher_session", owner_session)
    assert client.delete("/api/agentdesk/bind").status_code == 204
    assert client.get("/api/agentdesk/connection").json()["bound"] is False


def test_agentdesk_rejects_service_tokens_bad_responses_and_old_login(system, remote):
    client = system["client"]
    for action in ("bind", "link"):
        assert (
            client.post(f"/api/agentdesk/{action}", json={"token": "ad_integration"}).status_code
            == 401
        )
    assert remote["calls"] == 0
    remote["identity"]["active"] = False
    assert client.post("/api/agentdesk/bind", json={"token": "human-test-token"}).status_code == 503
    remote["identity"]["active"] = True
    remote["identity"]["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    assert client.post("/api/agentdesk/bind", json={"token": "human-test-token"}).status_code == 401
    remote["identity"]["expires_at"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    remote["identity"]["role"] = "member"
    assert client.post("/api/agentdesk/bind", json={"token": "human-test-token"}).status_code == 403
    remote["identity"]["role"] = "admin"
    connect(system)
    remote["identity"]["role"] = "viewer"
    assert (
        client.get(
            "/api/agentdesk/usage", headers={"Authorization": "Bearer human-test-token"}
        ).status_code
        == 403
    )
    from test_access import _SQL_AGE_SESSION

    with system["db"].auth() as connection:
        connection.execute(_SQL_AGE_SESSION, (system["owner"].subject_id,))
    assert client.post("/api/agentdesk/link", json={"token": "human-test-token"}).status_code == 401


def test_agentdesk_scheduled_roles_match_dashboard_and_session_totals(system, remote):
    connect(system)
    client = system["client"]

    def export(request):
        response = client.post(
            request.url.path,
            json=json.loads(request.content),
            headers={"Authorization": request.headers["Authorization"]},
        )
        return httpx.Response(response.status_code, content=response.content)

    monitor = Monitor(
        "http://testserver",
        system["key"]["secret"],
        "trader",
        "test",
        transport=httpx.MockTransport(export),
    )
    with monitor.context(session_id="agentdesk-scheduled-session", project="agentdesk"):
        with monitor.job("pipeline"):
            for work_item, role in (("TA1", "researcher"), ("TA2", "reviewer")):
                assert monitor.session_context(
                    "agentdesk-scheduled-session", work_item=work_item, pipeline_role=role
                )
                with monitor.operation(
                    provider="synthetic",
                    operation="complete",
                    resource_kind="llm",
                    reported_cost="0.01",
                    reported_currency="USD",
                ):
                    pass
    assert monitor.close() and monitor.failed == 0
    headers = {"Authorization": "Bearer human-test-token"}
    read = client.get("/api/agentdesk/sessions/agentdesk-scheduled-session", headers=headers).json()
    assert read["counts"]["attempts"] == 2
    assert {row["label"] for row in read["groups"]} == {"TA1", "TA2"}
    assert read["totals"] == client.get("/api/overview").json()["totals"]
    roles = client.get("/api/agentdesk/usage?group_by=pipeline_role", headers=headers).json()[
        "groups"
    ]
    assert {row["label"] for row in roles} == {"researcher", "reviewer"}

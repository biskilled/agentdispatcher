"""Authorization regressions use real sessions, multiple tenants, and PostgreSQL locks."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from dispatcher.membership import MembershipService
from fastapi import HTTPException
from test_integration import event, ingest

_SQL_AGE_SESSION = "UPDATE mng_sessions SET created_at=now()-interval '1 day' WHERE user_id=%s"
_SQL_EXPIRE_INVITE = "UPDATE mng_invitations SET expires_at=now()-interval '1 day' WHERE id=%s"


def invite_user(system, role="member"):
    """Invite a new mailbox and independently prove mailbox ownership before joining."""
    service = MembershipService(system["auth"])
    email = f"invite-{uuid4().hex}@example.test"
    invitation = service.invite(system["owner"], email, role)
    session = system["auth"].consume_login(system["auth"].request_login(email, email))
    user = system["auth"].user(session)
    assert user["tenants"] == []
    service.accept(user, invitation["token"])
    return session, user, invitation


def test_invite_requires_matching_identity_and_is_single_use(system):
    client = system["client"]
    session, user, invitation = invite_user(system)
    assert (
        client.post("/api/invitations/accept", json={"token": invitation["token"]}).status_code
        == 401
    )
    with pytest.raises(HTTPException) as error:
        MembershipService(system["auth"]).accept(user, invitation["token"])
    assert error.value.status_code == 401
    assert len(system["auth"].user(session)["tenants"]) == 1
    assert invitation["token"] not in str(client.get("/api/invitations").json())
    assert client.get("/api/members").status_code == 200
    assert (
        client.get(
            "/api/members", headers={"X-Tenant-ID": str(system["other"].tenant_id)}
        ).status_code
        == 403
    )


def test_invite_revocation_expiry_and_admin_escalation(system):
    service = MembershipService(system["auth"])
    session, user, _ = invite_user(system, "admin")
    admin = system["auth"].human(session, system["owner"].tenant_id)
    with pytest.raises(HTTPException) as error:
        service.invite(admin, "escape@example.test", "owner")
    assert error.value.status_code == 403
    for expired in (True, False):
        email = user["email"]
        invitation = service.invite(system["owner"], email, "member")
        if expired:
            with system["db"].auth() as connection:
                connection.execute(_SQL_EXPIRE_INVITE, (invitation["id"],))
        else:
            service.revoke(system["owner"], invitation["id"])
        with pytest.raises(HTTPException) as error:
            service.accept(user, invitation["token"])
        assert error.value.status_code == 401


def test_concurrent_owner_removal_preserves_owner(system):
    service = MembershipService(system["auth"])
    session, user, _ = invite_user(system, "owner")
    owners = [system["owner"], system["auth"].human(session, system["owner"].tenant_id)]

    def remove(principal):
        try:
            service.update(principal, principal.subject_id, None, [])
            return 204
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(remove, owners)) == [204, 409]
    survivor = next(
        p
        for p in owners
        if any(
            t["tenant_id"] == p.tenant_id
            for t in system["auth"].user(
                session
                if p.subject_id == user["user_id"]
                else system["client"].cookies.get("dispatcher_session")
            )["tenants"]
        )
    )
    assert len(service.members(survivor)) == 1


def test_verified_attribution_and_views_cannot_be_forged(system):
    client, auth = system["client"], system["auth"]
    session, user, _ = invite_user(system)
    tenant = system["owner"].tenant_id
    member = auth.human(session, tenant)
    assert ingest(system, [event(user_id=str(user["user_id"]))]).status_code == 202
    ledger = client.app.state.ledger
    assert ledger.overview(member)["counts"]["attempts"] == 0
    delegated = auth.delegate(session, tenant, "trader")
    headers = {
        "Authorization": "Bearer " + system["key"]["secret"],
        "X-User-Delegation": delegated["token"],
    }
    verified = event()
    assert (
        client.post("/api/ingest", json={"events": [verified]}, headers=headers).status_code == 202
    )
    assert ledger.overview(member)["counts"]["attempts"] == 1
    assert ledger.events(member)[0]["user_attribution"] == "verified"
    assert ingest(system, [verified]).status_code == 409
    wrong = auth.delegate(session, tenant, "another-app")
    assert (
        client.post(
            "/api/ingest",
            json={"events": [event()]},
            headers={**headers, "X-User-Delegation": wrong["token"]},
        ).status_code
        == 401
    )
    service = MembershipService(auth)
    service.update(system["owner"], user["user_id"], "viewer", ["different-app"])
    assert ledger.overview(auth.human(session, tenant))["counts"]["attempts"] == 0
    service.update(system["owner"], user["user_id"], "viewer", ["trader"])
    assert ledger.overview(auth.human(session, tenant))["counts"]["attempts"] == 2
    auth.logout(session)
    assert (
        client.post("/api/ingest", json={"events": [event()]}, headers=headers).status_code == 401
    )


def test_oidc_state_replay_and_recent_login(system):
    auth = system["auth"]
    state = auth.new_secret()
    auth.start_oidc(state)
    auth.consume_oidc(state)
    with pytest.raises(HTTPException) as error:
        auth.consume_oidc(state)
    assert error.value.status_code == 401
    session = system["client"].cookies.get("dispatcher_session")
    assert auth.recent_user(session)["user_id"] == system["owner"].subject_id
    with system["db"].auth() as connection:
        connection.execute(_SQL_AGE_SESSION, (system["owner"].subject_id,))
    with pytest.raises(HTTPException) as error:
        auth.recent_user(session)
    assert error.value.status_code == 401

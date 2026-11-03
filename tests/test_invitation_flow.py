"""Direct invitation acceptance preserves mailbox, tenant and current-role checks."""

from uuid import uuid4

import pytest
from dispatcher.api import create_app
from dispatcher.membership import MembershipService
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_access import _SQL_EXPIRE_INVITE, invite_user


def recipient(system):
    """Provision an invite and prove the mailbox without granting membership."""
    service = MembershipService(system["auth"])
    email = f"recipient-{uuid4().hex}@example.test"
    invitation = service.invite(system["owner"], email, "member")
    session = system["auth"].consume_login(system["auth"].request_login(email, email))
    return service, invitation, session, system["auth"].user(session)


def test_recipient_inbox_and_accept_without_token(system):
    service, invitation, session, user = recipient(system)
    client = system["client"]
    assert not user["tenants"]
    assert client.get("/api/invitations/pending").json() == []
    url = f"/api/invitations/{invitation['id']}/accept"
    assert client.post(url).status_code == 404
    client.cookies.set("dispatcher_session", session)
    del client.headers["X-Tenant-ID"]
    pending = client.get("/api/invitations/pending").json()
    assert [item["id"] for item in pending] == [str(invitation["id"])]
    assert pending[0]["workspace_name"] == "Tenant A"
    assert "token" not in str(pending)
    assert client.post(url, headers={"Origin": "https://foreign.test"}).status_code == 403
    response = client.post(url)
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(system["owner"].tenant_id)
    assert len(system["auth"].user(session)["tenants"]) == 1
    assert client.get("/api/invitations/pending").json() == []
    assert client.post(url).status_code == 401
    client.cookies.clear()
    assert client.get("/api/invitations/pending").status_code == 401


@pytest.mark.parametrize("expired", [True, False])
def test_direct_accept_rejects_expired_or_revoked(system, expired):
    service, invitation, _, user = recipient(system)
    if expired:
        with system["db"].auth() as connection:
            connection.execute(_SQL_EXPIRE_INVITE, (invitation["id"],))
    else:
        service.revoke(system["owner"], invitation["id"])
    assert service.pending(user) == []
    with pytest.raises(HTTPException) as error:
        service.accept_pending(user, invitation["id"])
    assert error.value.status_code == 401


def test_accept_rechecks_issuer_and_preserves_existing_role(system):
    service, invitation, session, user = recipient(system)
    service.accept_pending(user, invitation["id"])
    promotion = service.invite(system["owner"], user["email"], "owner")
    service.accept_pending(user, promotion["id"])
    assert system["auth"].human(session, system["owner"].tenant_id).role == "member"
    admin_session, admin_user, _ = invite_user(system, "admin")
    admin = system["auth"].human(admin_session, system["owner"].tenant_id)
    stale = service.invite(admin, user["email"], "member")
    service.update(system["owner"], admin_user["user_id"], "member", [])
    with pytest.raises(HTTPException) as error:
        service.accept_pending(user, stale["id"])
    assert error.value.status_code == 403


def test_unlinked_google_identity_does_not_inherit_email_invitations(system):
    service, invitation, _, user = recipient(system)
    session = system["auth"].google_login({
        "iss": "https://accounts.google.com", "sub": str(uuid4()),
        "email": user["email"], "email_verified": True,
    })
    google_user = system["auth"].user(session)
    assert service.pending(google_user) == []
    with pytest.raises(HTTPException) as error:
        service.accept_pending(google_user, invitation["id"])
    assert error.value.status_code == 403


@pytest.mark.parametrize("delivery", ["sent", "not_configured", "failed"])
def test_invitation_link_and_delivery_status(system, delivery):
    settings = system["db"].settings.model_copy(update={
        "smtp_sender": "sender@example.test" if delivery != "not_configured" else "",
    })
    mailer = system["mailer"]
    if delivery == "failed":
        def fail(email, url):
            raise OSError("fixture transport failure")
        mailer.send_invitation = fail
    with TestClient(create_app(settings, mailer)) as client:
        client.headers.update(system["client"].headers)
        client.cookies.update(system["client"].cookies)
        email = f"delivery-{uuid4().hex}@example.test"
        response = client.post("/api/invitations", json={"email": email, "role": "member"})
        assert response.status_code == 201
        result = response.json()
        assert result["delivery"] == delivery
        assert result["invitation_url"] == f"{settings.public_url}/#invite={result['id']}"
        assert result["token"] not in result["invitation_url"]
        if delivery == "sent":
            assert mailer.invitations == [(email, result["invitation_url"])]
        else:
            assert not mailer.invitations

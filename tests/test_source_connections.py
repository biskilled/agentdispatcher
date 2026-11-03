"""Source management changes metadata while preserving tenant and credential boundaries."""

import pytest
from dispatcher.gateway import Gateway
from fastapi import HTTPException
from test_access import invite_user

_SQL_GATEWAY_FIXTURE = "UPDATE mng_sdk_keys SET purpose='gateway',allowed_models=%s WHERE id=%s"


@pytest.mark.parametrize("source", ["sdk", "codex", "claude", "mcp"])
def test_source_classification_and_edit_preserve_scope(system, source):
    client = system["client"]
    response = client.post("/api/keys", json={
        "name": "Source fixture", "app": "fixture-app", "environment": "test",
        "source_type": source,
    })
    assert response.status_code == 201
    key = response.json()
    row = next(row for row in client.get("/api/keys").json() if row["id"] == key["id"])
    assert row["source_type"] == source
    assert "secret" not in row and "token_hash" not in row
    assert client.put(f"/api/keys/{key['id']}", json={
        "name": "Renamed", "source_type": "codex",
    }).status_code == 204
    row = next(row for row in client.get("/api/keys").json() if row["id"] == key["id"])
    assert row["name"] == "Renamed" and row["source_type"] == "codex"
    principal = system["auth"].service(key["secret"])
    assert principal.app == "fixture-app" and principal.environment == "test"
    assert client.put(f"/api/keys/{key['id']}", json={
        "name": "Escape", "app": "foreign-app",
    }).status_code == 422
    assert client.put(f"/api/keys/{key['id']}", json={
        "name": "Invalid", "source_type": "unrecognised",
    }).status_code == 422


def test_connection_edit_requires_admin_and_own_active_key(system):
    client, auth = system["client"], system["auth"]
    foreign = auth.issue_key(system["other"], "Other tenant", "app", "test")
    assert client.put(f"/api/keys/{foreign['id']}", json={"name": "Escape"}).status_code == 404
    key = system["key"]
    assert client.delete(f"/api/keys/{key['id']}").status_code == 204
    assert client.put(f"/api/keys/{key['id']}", json={"name": "Revoked"}).status_code == 404
    session, _, _ = invite_user(system, "member")
    client.cookies.set("dispatcher_session", session)
    assert client.put(f"/api/keys/{key['id']}", json={"name": "Forbidden"}).status_code == 403


def test_gateway_rename_preserves_purpose_and_allowed_models(system):
    key, db, client = system["key"], system["db"], system["client"]
    with db.auth() as connection:
        connection.execute(_SQL_GATEWAY_FIXTURE, (["fixture-model"], key["id"]))
    assert client.put(f"/api/keys/{key['id']}", json={
        "name": "Gateway name", "source_type": "codex",
    }).status_code == 204
    row = Gateway(db).keys(system["owner"])[0]
    assert row["name"] == "Gateway name" and row["allowed_models"] == ["fixture-model"]
    assert client.get("/api/keys").json() == []
    with pytest.raises(HTTPException) as error:
        system["auth"].service(key["secret"])
    assert error.value.status_code == 401

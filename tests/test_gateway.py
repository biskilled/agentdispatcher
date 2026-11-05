"""Virtual keys cannot impersonate SDK credentials; trusted callbacks still recheck scope."""

import json
import secrets
from uuid import uuid4

import httpx
import pytest
from dispatcher.policies import Policies
from dispatcher.policy_contracts import ModelPolicy
from fastapi import HTTPException
from pydantic import SecretStr
from test_integration import event, ingest


def test_gateway_key_scope_revocation_and_cost_provenance(system):
    client = system["client"]
    gateway = client.app.state.gateway
    upstream_key = None
    callback_secret = secrets.token_urlsafe(32)
    issued = []

    def upstream(request):
        nonlocal upstream_key
        assert request.url.path == "/key/generate"
        issued.append(json.loads(request.content))
        upstream_key = issued[-1]["key"]
        return httpx.Response(200, json={"key": upstream_key})

    gateway.settings = gateway.settings.model_copy(
        update={
            "gateway_url": "https://gateway.example.test",
            "gateway_master_key": SecretStr("fixture-master"),
            "gateway_callback_secret": SecretStr(callback_secret),
        }
    )
    gateway.transport = httpx.MockTransport(upstream)
    result = client.post(
        "/api/gateway/keys",
        json={"name": "LLM fixture", "app": "trader", "environment": "test", "models": ["model-a"]},
    )
    assert result.status_code == 201, result.text
    key = result.json()
    assert key["secret"] == upstream_key
    assert issued[0]["metadata"] == {"dispatcher_service_id": key["id"]}
    assert issued[0]["key_alias"] == key["id"]
    assert upstream_key not in str(client.get("/api/gateway/keys").json())
    assert all(row["id"] != key["id"] for row in client.get("/api/keys").json())
    assert (
        client.post(
            "/api/ingest",
            json={"events": [event()]},
            headers={"Authorization": "Bearer " + upstream_key},
        ).status_code
        == 401
    )
    headers = {"X-Gateway-Secret": callback_secret}
    authorised = {"service_id": key["id"], "model": "model-a"}
    assert (
        client.post("/internal/gateway/authorize", json=authorised, headers=headers).status_code
        == 200
    )
    assert (
        client.post(
            "/internal/gateway/authorize", json={**authorised, "model": "model-b"}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/internal/gateway/authorize", json=authorised, headers={"X-Gateway-Secret": "forged"}
        ).status_code
        == 401
    )
    observation = event(
        resource_kind="llm", source="litellm", reported_cost="0.125", reported_currency="USD"
    )
    body = {"service_id": key["id"], "event": observation}
    assert client.post("/internal/gateway/ingest", json=body, headers=headers).status_code == 202
    assert (
        client.post("/internal/gateway/ingest", json=body, headers=headers).json()["duplicates"]
        == 1
    )
    assert client.get("/api/events").json()[0]["cost_kind"] == "gateway_calculated"
    assert (
        client.post(
            "/internal/gateway/ingest",
            json={**body, "event": event(app="foreign")},
            headers=headers,
        ).status_code
        == 403
    )
    ingest(system, [event(reported_cost="0.25", reported_currency="USD")])
    assert client.get("/api/events").json()[0]["cost_kind"] == "app_estimate"
    assert client.delete("/api/keys/" + key["id"]).status_code == 204
    assert (
        client.post("/internal/gateway/authorize", json=authorised, headers=headers).status_code
        == 401
    )


@pytest.mark.parametrize(
    "response,state,models",
    [
        (
            httpx.Response(200, json={"data": [{"id": "model-a", "api_key": "private"}]}),
            "ready",
            ["model-a"],
        ),
        (httpx.Response(200, json={"data": []}), "no_models", []),
        (httpx.Response(401, text="private upstream detail"), "unavailable", []),
        (httpx.Response(200, json={"data": None}), "unavailable", []),
    ],
)
def test_gateway_connection_uses_native_model_list_without_provider_calls(
    system, response, state, models
):
    client = system["client"]
    gateway = client.app.state.gateway
    assert client.get("/api/gateway/connection").json()["state"] == "not_configured"

    def upstream(request):
        assert request.method == "GET" and request.url.path == "/v1/models"
        assert request.headers["Authorization"] == "Bearer operator-secret"
        return response

    gateway.settings = gateway.settings.model_copy(
        update={
            "gateway_url": "https://gateway.example.test",
            "gateway_master_key": SecretStr("operator-secret"),
            "gateway_client_url": "http://client.example.test/v1",
        }
    )
    gateway.transport = httpx.MockTransport(upstream)
    result = client.get("/api/gateway/connection")
    assert result.json() == {
        "state": state,
        "models": models,
        "base_url": "http://client.example.test/v1",
    }
    assert "private" not in result.text and "operator-secret" not in result.text
    client.headers["X-Tenant-ID"] = str(system["other"].tenant_id)
    assert client.get("/api/gateway/connection").status_code == 403


def test_native_services_default_scope_and_optimistic_updates(system):
    """Admins manage native aliases; default routing cannot cross key or tenant permissions."""
    client = system["client"]
    gateway = client.app.state.gateway
    info = {"aliases": {}, "metadata": {"operator_setting": "preserved"}}
    updates = []

    def upstream(request):
        if request.url.path == "/key/generate":
            body = json.loads(request.content)
            return httpx.Response(200, json={"key": body["key"]})
        if request.url.path == "/key/info":
            assert len(request.url.params["key"]) == 64
            return httpx.Response(200, json={"info": {**info, "key": "must-not-leak"}})
        assert request.url.path == "/key/update"
        update = json.loads(request.content)
        assert len(update["key"]) == 64
        updates.append(update)
        info.update(update)
        return httpx.Response(200, json=info)

    gateway.settings = gateway.settings.model_copy(
        update={
            "gateway_url": "https://gateway.example.test",
            "gateway_master_key": SecretStr("fixture-master"),
            "gateway_callback_secret": SecretStr("fixture-callback"),
        }
    )
    gateway.transport = httpx.MockTransport(upstream)
    key = client.post(
        "/api/gateway/keys",
        json={
            "name": "Trading",
            "app": "trader",
            "environment": "test",
            "models": ["model-a", "model-b"],
        },
    ).json()
    endpoint = f"/api/gateway/keys/{key['id']}/routing"
    current = client.get(endpoint)
    assert current.status_code == 200
    assert "must-not-leak" not in current.text and "operator_setting" not in current.text
    change = {
        "aliases": {"analysis": "model-a"},
        "default_model": "model-b",
        "revision": current.json()["revision"],
    }
    saved = client.put(endpoint, json=change)
    assert saved.status_code == 200, saved.text
    assert updates[-1]["models"] == ["*"]
    assert updates[-1]["metadata"]["operator_setting"] == "preserved"
    assert updates[-1]["metadata"]["dispatcher_service_id"] == key["id"]
    assert client.put(endpoint, json=change).status_code == 409
    change["revision"] = saved.json()["revision"]
    for bad in (
        {"aliases": {"analysis": "forbidden"}},
        {"default_model": "forbidden"},
        {"aliases": {"model-a": "model-b"}},
    ):
        assert client.put(endpoint, json={**change, **bad}).status_code == 400
    assert client.put(endpoint, json={**change, "aliases": {"*": "model-a"}}).status_code == 422
    headers = {"X-Gateway-Secret": "fixture-callback"}
    body = {"service_id": key["id"], "model": "typo", "default_model": "model-b"}
    routed = client.post("/internal/gateway/authorize", json=body, headers=headers)
    assert routed.status_code == 200, routed.text
    assert routed.json()["model"] == "model-b" and routed.json()["requested_model"] == "typo"
    assert (
        client.post(
            "/internal/gateway/authorize",
            json={**body, "default_model": "forbidden"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/internal/gateway/authorize", json={**body, "default_model": None}, headers=headers
        ).status_code
        == 403
    )
    known = client.post(
        "/internal/gateway/authorize", json={**body, "model": "model-a"}, headers=headers
    )
    assert known.json()["model"] == "model-a"
    principal = gateway.principal(key["id"])
    Policies(system["db"]).put(
        system["owner"],
        ModelPolicy(
            id="restricted",
            app="trader",
            environment="test",
            allowed_models=["model-a"],
        ),
        0,
    )
    with pytest.raises(HTTPException) as denied:
        gateway.route(principal, "typo", uuid4(), "model-b")
    assert denied.value.status_code == 403
    renamed = client.put(endpoint, json={**change, "aliases": {"research": "model-a"}})
    assert renamed.status_code == 200
    assert client.get(endpoint).json()["aliases"] == {"research": "model-a"}
    cleared = client.put(
        endpoint,
        json={"aliases": {}, "default_model": None, "revision": renamed.json()["revision"]},
    )
    assert cleared.status_code == 200
    assert updates[-1]["models"] == ["model-a", "model-b"]
    assert client.get(endpoint).json()["default_model"] is None
    client.headers["X-Tenant-ID"] = str(system["other"].tenant_id)
    assert client.get(endpoint).status_code == 403
    client.headers["X-Tenant-ID"] = str(system["owner"].tenant_id)
    assert client.get(f"/api/gateway/keys/{uuid4()}/routing").status_code == 404
    client.delete("/api/keys/" + key["id"])
    assert client.get(endpoint).status_code == 404
    assert client.post("/internal/gateway/authorize", json=body, headers=headers).status_code == 401

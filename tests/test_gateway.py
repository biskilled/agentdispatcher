"""Virtual keys cannot impersonate SDK credentials; trusted callbacks still recheck scope."""

import json
import secrets

import httpx
from pydantic import SecretStr
from test_integration import event, ingest


def test_gateway_key_scope_revocation_and_cost_provenance(system):
    client = system["client"]
    gateway = client.app.state.gateway
    upstream_key = "sk-" + secrets.token_urlsafe(32)
    callback_secret = secrets.token_urlsafe(32)
    issued = []

    def upstream(request):
        assert request.url.path == "/key/generate"
        issued.append(json.loads(request.content))
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

"""Verify native aliases/defaults with temporary mock models; never call paid providers."""

from uuid import uuid4

import httpx
from dispatcher.api import GatewayRoutingRequest
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.db import Database
from dispatcher.gateway import Gateway
from dispatcher.ledger import Ledger
from dispatcher.settings import get_settings
from gateway_smoke import wait_events


def verify():
    """Exercise two app keys on one public URL, then remove temporary models and revoke keys."""
    settings = get_settings()
    db = Database(settings)
    gateway, auth, ledger = Gateway(db), AuthService(db), Ledger(db)
    run = uuid4().hex
    owner = create_tenant(db, "Gateway services verification", f"gateway-{run}@example.test")
    models = [f"verify-{run}-{index}" for index in range(2)]
    model_ids, keys = [], []
    with gateway.client() as native:
        try:
            for index, model in enumerate(models):
                result = native.post(
                    "model/new",
                    json={
                        "model_name": model,
                        "litellm_params": {
                            "model": "openai/gpt-4o-mini",
                            "api_key": "synthetic-invalid-no-provider-access",
                            "mock_response": f"Synthetic service {index}",
                            "input_cost_per_token": 0.001,
                            "output_cost_per_token": 0.002,
                        },
                    },
                )
                result.raise_for_status()
                model_ids.append(result.json()["model_info"]["id"])
            for index, model in enumerate(models):
                key = gateway.issue(owner, f"App {index}", f"verify-app-{index}", "test", [model])
                keys.append(key)
                current = gateway.routing(owner, key["id"])
                gateway.routing(
                    owner,
                    key["id"],
                    GatewayRoutingRequest(
                        aliases={"analysis": model},
                        default_model=model,
                        revision=current["revision"],
                    ),
                )
            base = gateway.connection(owner)["base_url"]
            with httpx.Client(base_url=base.rstrip("/") + "/", timeout=30) as client:
                for index, key in enumerate(keys):
                    client.headers["Authorization"] = "Bearer " + key["secret"]
                    for name in ("analysis", "unknown-service"):
                        result = client.post(
                            "chat/completions",
                            json={
                                "model": name,
                                "messages": [{"role": "user", "content": "Synthetic test"}],
                            },
                        )
                        assert result.status_code == 200, (
                            f"Inference failed: HTTP {result.status_code}"
                        )
                        assert (
                            result.json()["choices"][0]["message"]["content"]
                            == f"Synthetic service {index}"
                        )
                rows = wait_events(ledger, owner, 4)
                assert {row["app"] for row in rows} == {"verify-app-0", "verify-app-1"}
                assert (
                    sum(row["payload"]["requested_model"] == "unknown-service" for row in rows) == 2
                )
                key = keys[0]
                current = gateway.routing(owner, key["id"])
                updated = gateway.routing(
                    owner,
                    key["id"],
                    GatewayRoutingRequest(
                        aliases={"renamed": models[0]},
                        default_model=None,
                        revision=current["revision"],
                    ),
                )
                assert updated["aliases"] == {"renamed": models[0]}
                assert gateway.routing(owner, key["id"])["default_model"] is None
                client.headers["Authorization"] = "Bearer " + key["secret"]
                body = {"messages": [{"role": "user", "content": "Synthetic test"}]}
                for name in ("analysis", "unknown-service", models[1]):
                    result = client.post("chat/completions", json={**body, "model": name})
                    assert result.status_code in {400, 401, 403}, (
                        f"Unauthorized model accepted: {name}"
                    )
                result = client.post("chat/completions", json={**body, "model": "renamed"})
                assert result.status_code == 200, f"Renamed alias failed: HTTP {result.status_code}"
                wait_events(ledger, owner, 5)
                auth.revoke_key(owner, key["id"])
                assert client.post(
                    "chat/completions", json={**body, "model": "renamed"}
                ).status_code in {401, 403}
            print(
                "PASS: native aliases, rename, per-app defaults, two-app attribution, "
                "default removal and revocation"
            )
        finally:
            for key in keys:
                auth.revoke_key(owner, key["id"])
                native.post("key/delete", json={"keys": [key["secret"]]}).raise_for_status()
            for model_id in model_ids:
                native.post("model/delete", json={"id": model_id}).raise_for_status()


if __name__ == "__main__":
    verify()

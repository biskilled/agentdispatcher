"""Exercise the real LiteLLM image using synthetic responses with no provider spend."""

import argparse
import time
from pathlib import Path

import httpx
import yaml
from dispatcher.auth import AuthService
from dispatcher.bootstrap import create_tenant
from dispatcher.db import Database
from dispatcher.gateway import Gateway
from dispatcher.ledger import Ledger
from dispatcher.policies import Policies
from dispatcher.policy_contracts import ModelPolicy
from dispatcher.settings import get_settings


def prepare(destination: Path, source: Path):
    """Derive fixture config from production config so callback/security settings stay identical."""
    config = yaml.safe_load(source.read_text())
    config["model_list"][0]["litellm_params"] = {
        "model": "openai/gpt-4o-mini",
        "api_key": "synthetic-no-network",
        "mock_response": "Synthetic response for AgentDispatcher integration verification.",
        "input_cost_per_token": 0.001,
        "output_cost_per_token": 0.002,
    }
    config["model_list"].append(
        {
            "model_name": "alternative-model",
            "litellm_params": {
                **config["model_list"][0]["litellm_params"],
                "model": "openai/gpt-4o",
            },
        }
    )
    destination.write_text(yaml.safe_dump(config))


def wait_events(ledger, owner, expected):
    """Wait for asynchronous callbacks, then assert the exact physical-attempt count."""
    deadline = time.monotonic() + 30
    rows = []
    while time.monotonic() < deadline:
        rows = ledger.events(owner)
        if len(rows) >= expected:
            break
        time.sleep(0.2)
    assert len(rows) == expected, f"Expected {expected} gateway attempts, observed {len(rows)}"
    return rows


def wait_ready(client):
    """Wait for the image's own schema initialization before creating virtual keys."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            if client.get("/health/liveliness").is_success:
                return
        except httpx.HTTPError:
            pass  # Readiness failures are expected while the container starts; deadline is fatal.
        time.sleep(1)
    raise RuntimeError("LiteLLM did not become ready")


def verify():
    """Verify model/tenant isolation, streaming accounting and immediate revocation."""
    settings = get_settings()
    db = Database(settings)
    gateway, auth, ledger = Gateway(db), AuthService(db), Ledger(db)
    with httpx.Client(base_url=settings.gateway_url, timeout=30) as client:
        wait_ready(client)
        for index in range(2):
            owner = create_tenant(
                db, f"Gateway synthetic tenant {index}", f"gateway-{index}@example.test"
            )
            key = gateway.issue(
                owner,
                "Synthetic LLM key",
                "fixture-app",
                "test",
                ["configured-model", "alternative-model"],
            )
            client.headers["Authorization"] = "Bearer " + key["secret"]
            body = {
                "model": "configured-model",
                "messages": [{"role": "user", "content": "Synthetic fixture only"}],
                "metadata": {
                    "dispatcher_context": {"project": "fixture", "work_item": "TA10008"},
                    "_dispatcher": {"scope": {"app": "forged"}},
                },
            }
            result = client.post("/v1/chat/completions", json=body)
            result.raise_for_status()
            streamed = client.post(
                "/v1/chat/completions",
                json={**body, "stream": True, "stream_options": {"include_usage": True}},
            )
            streamed.raise_for_status()
            rows = wait_events(ledger, owner, 2)
            assert all(row["app"] == "fixture-app" for row in rows)
            assert all(row["cost_kind"] == "gateway_calculated" for row in rows), rows
            policies = Policies(db)
            config = ModelPolicy(
                id="fixture-routing",
                app="fixture-app",
                environment="test",
                allowed_models=["configured-model", "alternative-model"],
                primary="configured-model",
            )
            policies.put(owner, config, 0)
            policies.put(owner, config.model_copy(update={"primary": "alternative-model"}), 1)
            routed = client.post("/v1/chat/completions", json=body)
            routed.raise_for_status()
            assert "gpt-4o" in routed.json()["model"] and "mini" not in routed.json()["model"]
            rows = wait_events(ledger, owner, 3)
            assert rows[0]["payload"]["requested_model"] == "configured-model"
            assert rows[0]["payload"]["policy_version"] == "fixture-routing:2"
            policies.rollback(owner, config.id, 2, 1)
            restored = client.post("/v1/chat/completions", json=body)
            restored.raise_for_status()
            assert "mini" in restored.json()["model"]
            assert (
                wait_events(ledger, owner, 4)[0]["payload"]["policy_version"] == "fixture-routing:3"
            )
            assert (
                client.post("/v1/chat/completions", json={**body, "model": "forbidden"}).status_code
                >= 400
            )
            auth.revoke_key(owner, key["id"])
            assert client.post("/v1/chat/completions", json=body).status_code >= 400
    print(
        "Real LiteLLM image: tenant/model restrictions, streaming, effective routing/rollback "
        "and revocation verified."
    )


def main():
    """Prepare host fixture configuration or run inside the configured API container."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", type=Path)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "services/gateway/config.yaml",
    )
    args = parser.parse_args()
    prepare(args.prepare, args.source) if args.prepare else verify()


if __name__ == "__main__":
    main()

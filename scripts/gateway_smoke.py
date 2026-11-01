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
    destination.write_text(yaml.safe_dump(config))


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
                owner, "Synthetic LLM key", "fixture-app", "test", ["configured-model"]
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
            deadline = time.monotonic() + 30
            rows = []
            while time.monotonic() < deadline:
                rows = ledger.events(owner)
                if len(rows) >= 2:
                    break
                time.sleep(0.2)
            assert len(rows) == 2, f"Expected two gateway attempts, observed {len(rows)}"
            assert all(row["app"] == "fixture-app" for row in rows)
            assert all(row["cost_kind"] == "gateway_calculated" for row in rows), rows
            assert (
                client.post("/v1/chat/completions", json={**body, "model": "forbidden"}).status_code
                >= 400
            )
            auth.revoke_key(owner, key["id"])
            assert client.post("/v1/chat/completions", json=body).status_code >= 400
    print(
        "Real LiteLLM image: tenant/model restrictions, streaming attempts and revocation verified."
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

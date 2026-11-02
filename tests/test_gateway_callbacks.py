"""Exercise LiteLLM hook contracts with synthetic retries and fallback responses."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import httpx


def test_policy_callback_requested_served_models_and_distinct_attempts(monkeypatch):
    """The real image smoke complements this isolated hook-order fixture."""
    litellm = ModuleType("litellm")
    litellm.completion_cost = lambda **kwargs: "0.2"
    logger = ModuleType("litellm.integrations.custom_logger")

    class Logger:
        def __init__(self, **kwargs):
            pass

    logger.CustomLogger = Logger
    monkeypatch.setitem(sys.modules, "litellm", litellm)
    monkeypatch.setitem(sys.modules, "litellm.integrations", ModuleType("litellm.integrations"))
    monkeypatch.setitem(sys.modules, "litellm.integrations.custom_logger", logger)
    monkeypatch.setenv("DISPATCHER_CALLBACK_URL", "https://fixture.test")
    monkeypatch.setenv("DISPATCHER_GATEWAY_CALLBACK_SECRET", "fixture-secret")
    path = Path(__file__).parents[1] / "services/gateway/dispatcher_callbacks.py"
    spec = importlib.util.spec_from_file_location("callbacks_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = module.proxy_handler
    observations = []
    assignment = str(uuid4())
    operation = str(uuid4())
    scope = {
        "service_id": str(uuid4()),
        "app": "fixture",
        "environment": "test",
        "model": "candidate-alias",
        "requested_model": "baseline-alias",
        "policy_version": "chat:1",
        "fallbacks": ["baseline-alias"],
        "experiment_id": str(uuid4()),
        "assignment_id": assignment,
        "variant": "candidate",
    }

    async def post(path, body):
        if path.endswith("authorize"):
            assert body["task_id"] == operation
            return httpx.Response(200, json=scope)
        observations.append(body["event"])
        return httpx.Response(202)

    handler._post = post

    async def run():
        key = SimpleNamespace(metadata={"dispatcher_service_id": scope["service_id"]})
        body = {
            "model": "baseline-alias",
            "metadata": {
                "dispatcher_context": {"operation_id": operation},
                "_dispatcher": {"scope": {"app": "spoof"}},
            },
            "fallbacks": [{"baseline-alias": ["unapproved"]}],
        }
        data = await handler.async_pre_call_hook(key, None, body, "completion")
        assert data["model"] == "candidate-alias"
        assert data["fallbacks"] == [{"candidate-alias": ["baseline-alias"]}]
        first = await handler.async_pre_call_deployment_hook(data, "completion")
        await handler.async_post_call_failure_deployment_hook(first, TimeoutError(), "completion")
        fallback = await handler.async_pre_call_deployment_hook(first, "completion")
        await handler.async_post_call_success_deployment_hook(
            fallback,
            {
                "model": "provider-baseline-model",
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                "choices": [{"message": {"content": "never export this body"}}],
            },
            "completion",
        )

    asyncio.run(run())
    assert len(observations) == 2
    assert observations[0]["attempt_id"] != observations[1]["attempt_id"]
    assert {row["operation_id"] for row in observations} == {operation}
    assert {row["assignment_id"] for row in observations} == {assignment}
    assert {row["requested_model"] for row in observations} == {"baseline-alias"}
    assert observations[1]["model"] == "provider-baseline-model"
    assert observations[0]["status"] == "timeout" and observations[1]["status"] == "success"
    assert "never export" not in str(observations)

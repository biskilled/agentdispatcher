"""Exercise LiteLLM hook contracts with synthetic retries and fallback responses."""

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import httpx
import pytest


@pytest.fixture
def handler(monkeypatch):
    """Load the real callback with only provider imports stubbed."""
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
    return module.proxy_handler


@pytest.mark.parametrize(
    "usage,standard",
    [
        ({"prompt_tokens": 4, "completion_tokens": 2}, {}),
        ({"input_tokens": 4, "output_tokens": 2}, {}),
        ({}, {"prompt_tokens": 4, "completion_tokens": 2, "response_cost": 0.125}),
    ],
)
def test_policy_callback_requested_served_models_and_distinct_attempts(handler, usage, standard):
    """The real image smoke complements this isolated hook-order fixture."""
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
        fallback["standard_logging_object"] = standard
        await handler.async_post_call_success_deployment_hook(
            fallback,
            {
                "model": "provider-baseline-model",
                "usage": usage,
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
    assert observations[1]["input_tokens"] == 4
    assert observations[1]["output_tokens"] == 2
    assert observations[1]["reported_cost"] == ("0.125" if standard else "0.2")


@pytest.mark.parametrize("override", [None, "api_key", "api_base", "model_list"])
def test_default_uses_trusted_key_metadata_and_overwrites_caller_routes(handler, override):
    """An app cannot set its default through request metadata or override the chosen provider."""
    from fastapi import HTTPException

    service_id = str(uuid4())

    async def post(path, body):
        assert body["default_model"] == "approved-model"
        assert body["model"] == "misspelled"
        return httpx.Response(
            200,
            json={
                "service_id": service_id,
                "app": "fixture",
                "environment": "test",
                "requested_model": "misspelled",
                "model": "approved-model",
                "policy_version": None,
                "fallbacks": [],
            },
        )

    handler._post = post

    async def run():
        key = SimpleNamespace(
            metadata={
                "dispatcher_service_id": service_id,
                "dispatcher_default_model": "approved-model",
            }
        )
        body = {
            "model": "misspelled",
            "fallbacks": [{"misspelled": ["forbidden"]}],
            "metadata": {"dispatcher_default_model": "forbidden"},
        }
        if override:
            body[override] = "forbidden"
            with pytest.raises(HTTPException) as denied:
                await handler.async_pre_call_hook(key, None, body, "completion")
            assert denied.value.status_code == 403
            return
        result = await handler.async_pre_call_hook(key, None, body, "completion")
        assert result["model"] == "approved-model"
        assert result["fallbacks"] == [{"approved-model": []}]
        assert result["metadata"]["_dispatcher"]["attributes"]["requested_model"] == "misspelled"

    asyncio.run(run())

"""LiteLLM OSS Python hooks: trusted scope, individual attempts and metadata-only accounting."""

import asyncio
import logging
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from litellm import completion_cost
from litellm.integrations.custom_logger import CustomLogger

_ATTRIBUTES = (
    "project",
    "work_item",
    "pipeline_role",
    "feature",
    "session_id",
    "trace_id",
    "job_run_id",
    "config_version",
    "user_id",
    "api_id",
)


class DispatcherCallbacks(CustomLogger):
    """Validate trusted virtual-key metadata; caller tags never determine tenant or app scope."""

    def __init__(self):
        super().__init__(turn_off_message_logging=True)
        self.endpoint = os.environ["DISPATCHER_CALLBACK_URL"].rstrip("/")
        self.secret = os.environ["DISPATCHER_GATEWAY_CALLBACK_SECRET"]
        self.timeout = float(os.environ.get("DISPATCHER_CALLBACK_TIMEOUT", "5"))
        self.attempts = int(os.environ.get("DISPATCHER_CALLBACK_ATTEMPTS", "3"))
        self.retry_delay = float(os.environ.get("DISPATCHER_CALLBACK_RETRY_DELAY", "0.25"))

    async def _post(self, path, body):
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.post(
                self.endpoint + path, json=body, headers={"X-Gateway-Secret": self.secret}
            )

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        """Block LLM execution when the registered key is revoked, unscoped or out of policy."""
        service_id = (getattr(user_api_key_dict, "metadata", None) or {}).get(
            "dispatcher_service_id"
        )
        if not service_id:
            raise HTTPException(403, "A Dispatcher-managed virtual key is required")
        metadata = dict(data.get("metadata") or {})
        context = metadata.get("dispatcher_context") or {}
        if not isinstance(context, dict):
            raise HTTPException(400, "dispatcher_context must be an object")
        try:
            operation = str(UUID(context.get("operation_id") or str(uuid4())))
            task_id = str(UUID(context.get("job_run_id") or operation))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(
                400, "Dispatcher operation and job identifiers must be UUIDs"
            ) from None
        try:
            response = await self._post(
                "/internal/gateway/authorize",
                {"service_id": service_id, "model": data.get("model", ""), "task_id": task_id},
            )
            if not response.is_success:
                raise HTTPException(403, "Virtual key or requested model is not authorised")
            scope = response.json()
        except httpx.HTTPError:
            raise HTTPException(503, "Dispatcher key verification is unavailable") from None
        attributes = {key: context[key] for key in _ATTRIBUTES if context.get(key) is not None}
        if any(not isinstance(value, str) or len(value) > 100 for value in attributes.values()):
            raise HTTPException(400, "Dispatcher context values must be short strings")
        attributes.update(
            {
                key: scope[key]
                for key in (
                    "requested_model",
                    "policy_version",
                    "experiment_id",
                    "assignment_id",
                    "variant",
                )
                if scope.get(key) is not None
            }
        )
        if scope.get("policy_version"):
            if any(
                key in data
                for key in (
                    "api_base",
                    "api_key",
                    "base_url",
                    "model_list",
                    "custom_llm_provider",
                )
            ):
                raise HTTPException(403, "Policy requests must use configured provider routes")
            data["model"] = scope["model"]
            data["fallbacks"] = [{scope["model"]: scope["fallbacks"]}]
            data["context_window_fallbacks"] = []
            data["content_policy_fallbacks"] = []
        metadata["_dispatcher"] = {
            "scope": scope,
            "operation_id": operation,
            "attributes": attributes,
            "started": datetime.now(UTC).isoformat(),
        }
        data["metadata"] = metadata
        return data

    def _state(self, data):
        metadata = data.get("metadata") or (data.get("litellm_params") or {}).get("metadata") or {}
        return metadata.get("_dispatcher")

    async def async_pre_call_deployment_hook(self, kwargs, call_type):
        """Assign fresh attempt IDs on retries/fallbacks while retaining the logical operation."""
        state = self._state(kwargs)
        if not state:
            raise HTTPException(403, "Missing verified Dispatcher context")
        metadata = dict(kwargs.get("metadata") or {})
        metadata["_dispatcher"] = {
            **state,
            "attempt_id": str(uuid4()),
            "started": datetime.now(UTC).isoformat(),
        }
        kwargs["metadata"] = metadata
        return kwargs

    async def async_post_call_success_deployment_hook(self, request_data, response, call_type):
        """Record non-streaming deployment attempts; terminal stream usage arrives via logging."""
        if not request_data.get("stream") and not hasattr(response, "__aiter__"):
            await self._emit(request_data, response, None)
        return response

    async def async_post_call_failure_deployment_hook(
        self, request_data, exception, call_type, fallback_depth=None
    ):
        """Retain every failed physical attempt, including failures preceding a successful retry."""
        await self._emit(request_data, None, exception)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        """Persist final stream usage and cache hits without duplicating normal deployment hooks."""
        standard = kwargs.get("standard_logging_object") or {}
        if kwargs.get("stream") or standard.get("cache_hit"):
            await self._emit(kwargs, response_obj, None, standard=standard, end=end_time)

    async def _emit(self, data, response, error, standard=None, end=None):
        state = self._state(data)
        if not state:
            logging.error("Dispatcher callback missing verified context; observation rejected")
            return
        standard = standard or {}
        payload = response.model_dump() if hasattr(response, "model_dump") else response or {}
        if not isinstance(payload, dict):
            payload = {}
        usage = payload.get("usage") or {}
        hidden = getattr(response, "_hidden_params", {}) or {}
        scope = state["scope"]
        attempt_id = state.get("attempt_id") or state["operation_id"]
        started = datetime.fromisoformat(state["started"])
        ended = end or datetime.now(UTC)
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=UTC)
        status = getattr(error, "status_code", None) if error else 200
        event = {
            "event_id": attempt_id,
            "attempt_id": attempt_id,
            "operation_id": state["operation_id"],
            "occurred_at": state["started"],
            "app": scope["app"],
            "environment": scope["environment"],
            "source": "litellm",
            "resource_kind": "llm",
            "provider": hidden.get("custom_llm_provider") or "litellm",
            "model": payload.get("model") or data.get("model"),
            "operation": "completion",
            "status": "timeout"
            if error and "timeout" in type(error).__name__.lower()
            else "error"
            if error
            else "cached"
            if standard.get("cache_hit")
            else "success",
            "status_code": status if isinstance(status, int) and 100 <= status <= 599 else None,
            "duration_ms": str(max(0, (ended - started).total_seconds() * 1000)),
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            **state["attributes"],
        }
        cost = standard.get("response_cost")
        if cost is None and not error:
            try:
                cost = completion_cost(completion_response=response, model=data.get("model"))
            except Exception:
                logging.warning("LiteLLM pricing unavailable; Dispatcher will retain unknown cost")
        if cost is not None and not standard.get("zero_cost_diagnostic"):
            event.update(reported_cost=str(cost), reported_currency="USD")
        body = {"service_id": scope["service_id"], "event": event}
        for attempt in range(self.attempts):
            try:
                exported = await self._post("/internal/gateway/ingest", body)
                if exported.is_success:
                    return
                if exported.status_code < 500 and exported.status_code != 429:
                    logging.error(
                        "Dispatcher rejected gateway observation: status=%s", exported.status_code
                    )
                    return
            except httpx.HTTPError:
                logging.warning("Dispatcher gateway export unavailable")
            if attempt + 1 < self.attempts:
                await asyncio.sleep(self.retry_delay * (2**attempt))
        logging.error("Dispatcher gateway observation lost after export retry limit")


proxy_handler = DispatcherCallbacks()

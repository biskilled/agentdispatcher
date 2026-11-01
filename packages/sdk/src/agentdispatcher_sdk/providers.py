"""Observe an existing shared provider client without changing business requests or retries."""

import logging


class ProviderObserver:
    """Accept completed in-memory results; export only explicit usage counters and model labels."""

    def __init__(self, monitor, providers: dict[str, dict]):
        self.monitor, self.providers = monitor, providers

    def __call__(self, provider: str, result, error: Exception | None, duration_ms: float):
        """Observe one attempt; the integrating client owns exceptions and retries."""
        config = self.providers.get(provider)
        if config is None:
            return
        try:
            self._record(provider, config, result, error, duration_ms)
        except Exception:
            # Monitoring must not replace the business exception, and errors must not log payloads.
            logging.error("Provider observation failed; original business outcome retained")

    def _record(self, provider, config, result, error, duration_ms):
        response = getattr(error, "response", None) if error else result
        status_code = getattr(response, "status_code", None)
        kind = config.get("resource_kind", "api")
        metadata = {"api_id": config.get("api_id", provider), "source": "provider-observer"}
        if isinstance(status_code, int) and 100 <= status_code <= 599:
            metadata["status_code"] = status_code
        if config.get("connection_id"):
            metadata["connection_id"] = config["connection_id"]
        if kind == "llm" and response is not None:
            payload = response if isinstance(response, dict) else None
            if payload is None and getattr(response, "is_stream_consumed", False):
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
            if isinstance(payload, dict):
                usage = payload.get("usage") or {}
                if isinstance(usage, dict):
                    for field, alias in (
                        ("input_tokens", "prompt_tokens"),
                        ("output_tokens", "completion_tokens"),
                    ):
                        value = usage.get(field, usage.get(alias))
                        if type(value) is int and value >= 0:
                            metadata[field] = value
                model = payload.get("model")
                if isinstance(model, str) and len(model) <= 200:
                    metadata["model"] = model
        status = "success"
        if error or (isinstance(status_code, int) and status_code >= 400):
            status = "timeout" if error and "timeout" in type(error).__name__.lower() else "error"
        self.monitor.record(
            provider=provider,
            operation=config.get("operation", "request"),
            resource_kind=kind,
            status=status,
            duration_ms=duration_ms,
            **metadata,
        )

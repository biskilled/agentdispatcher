"""Optional server-side credential mapping for applications that serve several tenants."""

import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

from agentdispatcher_sdk.client import Monitor
from agentdispatcher_sdk.providers import ProviderObserver

_scope = ContextVar("dispatcher_registry_scope", default=None)


class MonitorRegistry:
    """Resolve trusted tenant IDs to explicit keys; never infer scope from email or tags."""

    def __init__(self, bindings: dict, factory=Monitor):
        self.bindings, self.factory = bindings, factory
        self.monitors, self._lock = {}, Lock()
        self.unmapped_scopes = 0
        self.setup_failures = 0
        self._warned = set()
        for binding in bindings.values():
            if not isinstance(binding, dict) or not all(
                isinstance(binding.get(field), str) and binding[field]
                for field in ("endpoint_env", "key_env", "app", "environment")
            ):
                raise ValueError("Monitor bindings require endpoint/key env names and app scope")
            for provider, config in binding.get("providers", {}).items():
                if not isinstance(provider, str) or not isinstance(config, dict):
                    raise ValueError("Provider observation configuration is invalid")
                if config.get("resource_kind", "api") not in ("api", "llm", "tool"):
                    raise ValueError("Unknown provider resource kind")

    @classmethod
    def from_environment(cls, variable: str):
        """Load explicit operator bindings; values contain environment references, never keys."""
        bindings = json.loads(os.environ.get(variable, "{}"))
        if not isinstance(bindings, dict):
            raise ValueError("Monitor bindings must be a JSON object")
        return cls(bindings)

    def _get(self, scope_id):
        binding = self.bindings.get(scope_id)
        if not binding:
            with self._lock:
                self.unmapped_scopes += 1
                if self.bindings and scope_id not in self._warned:
                    logging.warning(
                        "Dispatcher scope has no configured credential; usage is uncovered"
                    )
                    self._warned.add(scope_id)
            return None
        with self._lock:
            if scope_id not in self.monitors:
                try:
                    self.monitors[scope_id] = self.factory(
                        endpoint=os.environ[binding["endpoint_env"]],
                        key=os.environ[binding["key_env"]],
                        app=binding["app"],
                        environment=binding["environment"],
                    )
                except Exception:
                    self.setup_failures += 1
                    logging.error(
                        "Dispatcher monitor setup failed; application execution continues"
                    )
                    return None
            return self.monitors[scope_id]

    @contextmanager
    def scope(self, trusted_scope_id, job_name=None, **attributes):
        """Bind only after application authorization or a trusted database/queue tenant lookup."""
        scope_id = str(trusted_scope_id) if trusted_scope_id is not None else ""
        monitor = self._get(scope_id)
        current = _scope.get()
        if current and current == (id(self), scope_id):
            yield monitor
            return
        token = _scope.set((id(self), scope_id))
        try:
            if monitor is None:
                yield None
            else:
                binding = self.bindings[scope_id]
                context = dict(binding.get("context", {}))
                if binding.get("config_version_env"):
                    context["config_version"] = os.environ.get(binding["config_version_env"])
                with monitor.context(**{**context, **attributes}):
                    if job_name:
                        with monitor.job(job_name):
                            yield monitor
                    else:
                        yield monitor
        finally:
            _scope.reset(token)

    def observer(self, trusted_scope_id, monitor):
        """Create a shared-client observer using only the scope's explicit provider allowlist."""
        if monitor is None:
            return None
        config = self.bindings[str(trusted_scope_id)]
        return ProviderObserver(monitor, config.get("providers", {}))

    def close(self):
        """Flush monitors at application shutdown; return visible exporter coverage counters."""
        return {
            scope_id: {
                "flushed": monitor.close(),
                "failed": monitor.failed,
                "dropped": monitor.dropped,
                "delivered": monitor.delivered,
            }
            for scope_id, monitor in self.monitors.items()
        }

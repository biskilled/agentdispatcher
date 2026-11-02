"""Optional AgentData gateway bridge; copy into backend/core with the accompanying patch."""

import atexit
import hashlib
import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from functools import lru_cache

_prompt = ContextVar("dispatcher_prompt", default=None)
_gateway = ContextVar("dispatcher_gateway", default=None)


@lru_cache(maxsize=1)
def registry():
    """Load only explicit operator bindings; an absent configuration has no SDK dependency."""
    if not os.environ.get("AGENTDATA_DISPATCHER_BINDINGS"):
        return None
    from agentdispatcher_sdk.registry import MonitorRegistry

    value = MonitorRegistry.from_environment("AGENTDATA_DISPATCHER_BINDINGS")
    atexit.register(value.close)
    return value


@contextmanager
def prompt_context(key, configuration, **effective):
    """Attribute the effective loaded prompt configuration by digest, never by its content."""
    digest = hashlib.sha256(
        json.dumps(
            {**asdict(configuration), **effective}, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    token = _prompt.set({"feature": key, "config_version": digest})
    try:
        yield
    finally:
        _prompt.reset(token)


def gateway_metadata():
    """Supply attribution only while executing a configured gateway call."""
    return _gateway.get()


def complete(function, provider, system, user, model, max_tokens, **options):
    """Route opted-in tenants through their own gateway key; the gateway owns billing."""
    from core import llm
    from core.tenant import current_client_id, current_user_id

    monitors = registry()
    tenant = current_client_id.get()
    if monitors is None:
        return function(system, user, model, max_tokens, **options)
    binding = monitors.bindings.get(str(tenant))
    if not binding:
        # A global or unbound call must never inherit another tenant's routing or SDK key.
        logging.warning("AgentData Dispatcher binding missing; this call is not monitored")
        return function(system, user, model, max_tokens, **options)
    endpoint = os.environ[binding["gateway_endpoint_env"]]
    key = os.environ[binding["gateway_key_env"]]
    from core import security

    security.assert_provider_egress(tenant, "openai", endpoint)
    attributes = dict(_prompt.get() or {})
    if current_user_id.get() is not None:
        attributes["user_id"] = str(current_user_id.get())
    with monitors.scope(tenant, **attributes) as monitor:
        connection = llm.Connection(provider="openai", base_url=endpoint, api_key=key)
        with llm.use_connection(connection):
            if monitor is None:
                # Monitoring delivery/setup errors cannot redirect an already configured request.
                return llm._openai_compatible(system, user, model, max_tokens, **options)
            with monitor.gateway() as context:
                token = _gateway.set(context)
                try:
                    return llm._openai_compatible(system, user, model, max_tokens, **options)
                finally:
                    _gateway.reset(token)

"""Optional AgentDispatcher bridge; enabled only by explicit server-side tenant bindings."""

import atexit
import inspect
import logging
from contextlib import contextmanager
from contextvars import copy_context
from functools import lru_cache, wraps

from agenttrade_sdk.provider_operations import observe_provider_calls


@lru_cache(maxsize=1)
def _registry():
    import os

    if not os.environ.get("AGENTTRADE_DISPATCHER_BINDINGS"):
        return None
    try:
        from agentdispatcher_sdk.registry import MonitorRegistry

        registry = MonitorRegistry.from_environment("AGENTTRADE_DISPATCHER_BINDINGS")
    except Exception:
        logging.error("AgentDispatcher unavailable; check package and binding configuration")
        return None
    atexit.register(registry.close)
    return registry


@contextmanager
def monitor_scope(organisation_id, job_name=None, **attributes):
    """Enter after trusted organisation resolution; global scope cannot inherit a tenant key."""
    registry = _registry()
    if registry is None:
        yield
        return
    with registry.scope(organisation_id, job_name=job_name, **attributes) as monitor:
        with observe_provider_calls(registry.observer(organisation_id, monitor)):
            yield


def monitor_job(name, organisation_parameter="organisation_id"):
    """Instrument a synchronous business entrypoint once, preserving its return and exception."""

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs)
            arguments.apply_defaults()
            with monitor_scope(arguments.arguments.get(organisation_parameter), job_name=name):
                return function(*args, **kwargs)

        return wrapped

    return decorate


def submit_context(executor, function, *args, **kwargs):
    """Copy job/tenant attribution independently for each thread-pool submission."""
    return executor.submit(copy_context().run, function, *args, **kwargs)

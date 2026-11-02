"""Opt-in HTTPX transports measure physical attempts without inspecting bodies or URLs."""

import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from agentdispatcher_sdk.client import Monitor


class _TransportObservation:
    """Share sync/async measurement and correlation; subclasses own only transport calls."""

    def __init__(
        self,
        monitor: Monitor,
        transport,
        *,
        provider: str,
        api_id: str,
        operation: str,
        connection_id: str | None = None,
        canonical_source: str | None = None,
    ):
        self.monitor, self.transport = monitor, transport
        self.metadata = {
            "provider": provider,
            "api_id": api_id,
            "operation": operation,
            "connection_id": connection_id,
            "canonical_source": canonical_source,
            "source": "python-http",
        }

    @contextmanager
    def observe(self, request):
        """Attach safe identifiers so a provider observer can reuse the same physical attempt."""
        metadata = {
            **self.metadata,
            "attempt_id": str(uuid4()),
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        with self.monitor.operation(**metadata) as measured:
            correlation = {
                key: measured[key]
                for key in (
                    "attempt_id",
                    "operation_id",
                    "occurred_at",
                    "source",
                    "canonical_source",
                )
            }
            request.extensions["dispatcher_correlation"] = correlation
            try:
                yield measured, correlation
            except Exception as error:
                try:
                    error.dispatcher_correlation = correlation
                except (AttributeError, TypeError):
                    logging.warning(
                        "Exception does not support monitoring correlation; original error retained"
                    )
                raise

    def received(self, response, measured, correlation):
        """Leave streaming bodies untouched and retain a reference on the in-memory response."""
        response.extensions["dispatcher_correlation"] = correlation
        measured.update(
            status_code=response.status_code, status="error" if response.is_error else "success"
        )
        return response


class MonitoredTransport(_TransportObservation, httpx.BaseTransport):
    """Wrap a caller-owned transport with safe provider/API/operation labels."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Record response-header latency and outcome, without consuming the body."""
        with self.observe(request) as (measured, correlation):
            return self.received(self.transport.handle_request(request), measured, correlation)

    def close(self) -> None:
        """Close the underlying transport, leaving monitor lifetime to the application."""
        self.transport.close()


class AsyncMonitoredTransport(_TransportObservation, httpx.AsyncBaseTransport):
    """Async counterpart sharing the same measurement and correlation implementation."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Preserve caller exceptions and avoid consuming streaming response bodies."""
        with self.observe(request) as (measured, correlation):
            return self.received(
                await self.transport.handle_async_request(request), measured, correlation
            )

    async def aclose(self) -> None:
        """Close the caller-owned asynchronous transport."""
        await self.transport.aclose()

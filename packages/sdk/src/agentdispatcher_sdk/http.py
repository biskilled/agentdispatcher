"""Opt-in HTTPX transports measure each network attempt without inspecting bodies or URLs."""

import httpx

from agentdispatcher_sdk.client import Monitor


class MonitoredTransport(httpx.BaseTransport):
    """Wrap a caller-owned transport; supply a safe operation template, never a raw URL."""

    def __init__(
        self,
        monitor: Monitor,
        transport: httpx.BaseTransport,
        *,
        provider: str,
        api_id: str,
        operation: str,
        connection_id: str | None = None,
    ):
        self.monitor, self.transport = monitor, transport
        self.metadata = {
            "provider": provider,
            "api_id": api_id,
            "operation": operation,
            "connection_id": connection_id,
        }

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Record response-header latency and outcome; leave response streaming untouched."""
        with self.monitor.operation(**self.metadata) as measured:
            response = self.transport.handle_request(request)
            measured.update(
                status_code=response.status_code, status="error" if response.is_error else "success"
            )
            return response

    def close(self) -> None:
        """Close the underlying transport, leaving monitor lifetime to the application."""
        self.transport.close()


class AsyncMonitoredTransport(httpx.AsyncBaseTransport):
    """Async counterpart using the same measurement contract and background exporter."""

    def __init__(
        self,
        monitor: Monitor,
        transport: httpx.AsyncBaseTransport,
        *,
        provider: str,
        api_id: str,
        operation: str,
        connection_id: str | None = None,
    ):
        self.monitor, self.transport = monitor, transport
        self.metadata = {
            "provider": provider,
            "api_id": api_id,
            "operation": operation,
            "connection_id": connection_id,
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Preserve caller exceptions and avoid consuming streaming response bodies."""
        with self.monitor.operation(**self.metadata) as measured:
            response = await self.transport.handle_async_request(request)
            measured.update(
                status_code=response.status_code, status="error" if response.is_error else "success"
            )
            return response

    async def aclose(self) -> None:
        """Close the caller-owned asynchronous transport."""
        await self.transport.aclose()

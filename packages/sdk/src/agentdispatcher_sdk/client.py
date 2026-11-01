"""Business requests never wait for telemetry delivery or inherit exporter failures."""

import contextvars
import logging
import queue
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from opentelemetry import trace

_run = contextvars.ContextVar("dispatcher_run", default=None)
_context = contextvars.ContextVar("dispatcher_context", default=None)
_delegation = contextvars.ContextVar("dispatcher_user_delegation", default=None)
_CONTEXT_FIELDS = frozenset(
    {"project", "work_item", "session_id", "trace_id", "user_id", "config_version", "job_run_id"}
)


class Monitor:
    """Export scoped usage in a bounded background queue; close during app shutdown."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        app: str,
        environment: str,
        capacity: int = 1000,
        timeout: float = 5,
        attempts: int = 3,
        retry_delay: float = 0.5,
        transport=None,
    ):
        if capacity <= 0 or attempts <= 0 or timeout <= 0 or retry_delay < 0:
            raise ValueError("Invalid exporter limits")
        self.app, self.environment = app, environment
        self.attempts, self.retry_delay = attempts, retry_delay
        self.dropped = 0
        self.failed = 0
        self.delivered = 0
        self._closed = False
        self._lock = threading.Lock()
        self._queue = queue.Queue(maxsize=capacity)
        self._stop = threading.Event()
        self._client = httpx.Client(
            base_url=endpoint.rstrip("/") + "/",
            headers={"Authorization": "Bearer " + key},
            timeout=timeout,
            transport=transport,
        )
        self._thread = threading.Thread(target=self._worker, name="dispatcher-export", daemon=True)
        self._thread.start()

    def _enqueue(self, path: str, payload: dict) -> bool:
        with self._lock:
            if self._closed:
                self.dropped += 1
                return False
            try:
                self._queue.put_nowait((path, payload, _delegation.get()))
                return True
            except queue.Full:
                self.dropped += 1
                logging.warning("Dispatcher telemetry queue full; event dropped")
                return False

    def record(
        self,
        *,
        provider: str,
        operation: str,
        resource_kind: str,
        status: str,
        duration_ms: float,
        **metadata,
    ) -> str:
        """Record one physical attempt; retrying export preserves its original identifiers."""
        event_id = str(uuid4())
        span = trace.get_current_span().get_span_context()
        run = _run.get()
        payload = {
            "event_id": event_id,
            "attempt_id": str(uuid4()),
            "operation_id": str(uuid4()),
            "occurred_at": datetime.now(UTC).isoformat(),
            "app": self.app,
            "environment": self.environment,
            "source": "python-sdk",
            "resource_kind": resource_kind,
            "provider": provider,
            "operation": operation,
            "status": status,
            "duration_ms": str(duration_ms),
            **(_context.get() or {}),
            **metadata,
        }
        if run:
            payload.setdefault("job_run_id", run["run_id"])
            payload.setdefault("trace_id", run["trace_id"])
        if span.is_valid:
            payload["trace_id"] = format(span.trace_id, "032x")
        self._enqueue("api/ingest", {"events": [payload]})
        return event_id

    @contextmanager
    def context(self, **attributes):
        """Scope metadata to a request/task; reported IDs never become authenticated identity."""
        if attributes.keys() - _CONTEXT_FIELDS:
            raise ValueError("Unsupported attribution attribute")
        context = _context.set({**(_context.get() or {}), **attributes})
        try:
            yield
        finally:
            _context.reset(context)

    @contextmanager
    def user(self, delegation: str):
        """Attach short-lived consent from /auth/delegate without putting it into event metadata."""
        context = _delegation.set(delegation)
        try:
            yield
        finally:
            _delegation.reset(context)

    def export_context(self) -> dict:
        """Copy metadata for an explicit queue message; credentials are always excluded."""
        attributes = dict(_context.get() or {})
        if run := _run.get():
            attributes.update(job_run_id=run["run_id"], trace_id=run["trace_id"])
        return attributes

    @contextmanager
    def operation(self, *, provider: str, operation: str, resource_kind: str = "api", **metadata):
        """Wrap one actual provider attempt; fill response units/status in the yielded mapping."""
        measurements = dict(metadata)
        started = time.monotonic()
        status = "success"
        try:
            yield measurements
        except httpx.TimeoutException:
            status = "timeout"
            raise
        except Exception:
            status = "error"
            raise
        finally:
            reported_status = measurements.pop("status", status)
            if status == "success":
                status = reported_status
            self.record(
                provider=provider,
                operation=operation,
                resource_kind=resource_kind,
                status=status,
                duration_ms=(time.monotonic() - started) * 1000,
                **measurements,
            )

    @contextmanager
    def job(self, name: str, *, schedule_id: str | None = None, scheduled_for: str | None = None):
        """Attach concurrent-safe run context to calls; propagate explicitly across queues."""
        run = {
            "run_id": str(uuid4()),
            "trace_id": uuid4().hex,
            "name": name,
            "app": self.app,
            "environment": self.environment,
        }
        if (schedule_id is None) != (scheduled_for is None):
            raise ValueError("schedule_id and scheduled_for must be provided together")
        if schedule_id:
            run.update(schedule_id=schedule_id, scheduled_for=scheduled_for)
        context = _run.set(run)
        state = "completed"
        self._job_event(run, "running")
        try:
            yield run
        except BaseException:
            state = "failed"
            raise
        finally:
            self._job_event(run, state)
            _run.reset(context)

    def heartbeat(self) -> None:
        """Refresh the current long-running job's health without emitting a billable attempt."""
        if (run := _run.get()) is not None:
            self._job_event(run, "running")

    def _job_event(self, run: dict, state: str) -> None:
        self._enqueue(
            "api/jobs/events", {**run, "state": state, "occurred_at": datetime.now(UTC).isoformat()}
        )

    def _deliver(self, path: str, payload: dict, delegation: str | None) -> bool:
        for attempt in range(self.attempts):
            try:
                headers = {"X-User-Delegation": delegation} if delegation else None
                response = self._client.post(path, json=payload, headers=headers)
                if response.is_success:
                    return True
                if response.status_code < 500 and response.status_code != 429:
                    logging.warning("Dispatcher export rejected: status=%s", response.status_code)
                    return False
            except httpx.TransportError:
                logging.warning("Dispatcher export transport failed")
            if attempt + 1 < self.attempts:
                self._stop.wait(self.retry_delay * (2**attempt))
        return False

    def _worker(self) -> None:
        try:
            while not self._stop.is_set() or not self._queue.empty():
                try:
                    path, payload, delegation = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    if self._deliver(path, payload, delegation):
                        self.delivered += 1
                    else:
                        self.failed += 1
                except Exception:
                    self.failed += 1
                    logging.error("Dispatcher exporter failed; event discarded")
                finally:
                    self._queue.task_done()
        finally:
            self._client.close()

    def close(self, timeout: float = 10) -> bool:
        """Try to drain within a deadline; return false if the daemon is still draining."""
        with self._lock:
            self._closed = True
        self._stop.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logging.warning("Dispatcher flush deadline exceeded; pending telemetry may be lost")
            return False
        return True

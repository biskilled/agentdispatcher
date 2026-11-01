"""Run AgentTrade's real scheduler/meter with synthetic providers; no financial operations."""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import httpx


def main():
    """Receive fixture credentials over stdin, then exercise real scoped scheduler code."""
    setup = json.load(sys.stdin)
    os.environ.update(setup["environment"])
    os.environ.pop("REDIS_URL", None)
    from agenttrade_sdk import get_logger, meter_provider
    from agenttrade_sdk.dispatcher_monitoring import _registry, submit_context
    from app.domain import scheduler_tasks

    def llm():
        return meter_provider(
            "fixture-llm",
            lambda: httpx.Response(
                200,
                json={
                    "model": "fixture-model",
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                    "content": "Synthetic private prompt/result; must never leave the application",
                },
            ),
        )

    def timeout():
        raise httpx.ReadTimeout("Synthetic timeout")

    def runner(config, organisation_id=None):
        if config.get("fail"):
            llm()
            raise ValueError("Synthetic business failure")
        with ThreadPoolExecutor(max_workers=2) as pool:
            submit_context(pool, llm).result()
            for status in (429, 200):
                submit_context(
                    pool,
                    meter_provider,
                    "fixture-market",
                    lambda code=status: httpx.Response(
                        code,
                        json={},
                        request=httpx.Request("GET", "https://fixture.example.test/price"),
                    ),
                ).result()
        try:
            meter_provider("fixture-llm", timeout)
        except httpx.ReadTimeout:
            pass  # This fixture explicitly models an app recovering from a provider timeout.
        return {"assets_updated": 0}

    recorded = []

    @contextmanager
    def database():
        yield SimpleNamespace(execute=lambda _sql, values: recorded.append(values))

    with (
        patch.object(scheduler_tasks, "db", database),
        patch.object(scheduler_tasks, "TASK_REGISTRY", {"dispatcher-fixture": {"runner": runner}}),
    ):
        for organisation in setup["organisations"]:
            for fail in (False, True):
                scheduler_tasks._execute_task(
                    {
                        "id": "synthetic-task",
                        "name": "Synthetic monitoring",
                        "task_type": "dispatcher-fixture",
                        "organisation_id": organisation,
                        "config": {"fail": fail},
                    },
                    get_logger(),
                )
    counters = _registry().close()
    assert len(recorded) == 4
    assert [row[6] for row in recorded] == ["completed", "failed", "completed", "failed"]
    assert all(
        row["flushed"] and not row["failed"] and not row["dropped"] for row in counters.values()
    )
    print("AgentTrade scheduler and thread-pool provider observation exported successfully.")


if __name__ == "__main__":
    main()

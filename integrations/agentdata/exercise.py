"""Exercise actual AgentData PostgreSQL discovery and patched shared LLM/prompt entry points."""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import text

_SQL_COUNTS = "SELECT count(*) attempts,sum(input_tokens) input_tokens FROM llm_usage"
_SQL_COST = "SELECT currency,cost_kind,sum(cost) cost FROM llm_usage GROUP BY currency,cost_kind"
_SQL_GROUPS = "SELECT provider,count(*) attempts FROM llm_usage GROUP BY provider"
_SQL_FORGED = "SELECT count(*) FROM llm_usage WHERE tenant_id=:tenant"


def main():
    """Use fixture credentials supplied over stdin; never write the production registry."""
    setup = json.load(sys.stdin)
    os.environ.update(setup["environment"])
    from adapters.relational import RelationalAdapter
    from core import dispatcher_monitoring, security, usage
    from core.config import settings
    from core.prompt_loader import PromptLoader
    from core.tenant import current_client_id

    for item in setup["tenants"]:
        adapter = RelationalAdapter(item["url"])
        try:
            adapter.test_connection()
            assert "llm_usage" in adapter.list_objects()
            profile = adapter.profile_object("llm_usage", sample_rows=10)
            assert profile.object_type == "view"
            assert not adapter.capabilities()["write"]
            with adapter._eng().connect() as connection:
                counts = connection.execute(text(_SQL_COUNTS)).mappings().one()
                assert counts["attempts"] == item["attempts"]
                assert int(counts["input_tokens"]) == item["tokens"]
                costs = connection.execute(text(_SQL_COST)).mappings().all()
                assert {(r["currency"], r["cost_kind"]): str(r["cost"]) for r in costs} == {
                    (r["currency"], r["cost_kind"]): str(Decimal(r["cost"])) for r in item["totals"]
                }
                groups = connection.execute(text(_SQL_GROUPS)).mappings().all()
                assert {r["provider"]: r["attempts"] for r in groups} == item["providers"]
                assert (
                    connection.execute(text(_SQL_FORGED), {"tenant": item["other"]}).scalar() == 0
                )
        finally:
            adapter._eng().dispose()

    with TemporaryDirectory(prefix="agentdata-prompt-") as directory:
        prompt = Path(directory) / "fixture.yaml"
        prompt.write_text(
            "- key: fixture_summary\n  provider: openai\n  model: fixture-model\n"
            '  max_tokens: 20\n  system: "Synthetic private system"\n'
            '  template: "Synthetic private user"\n'
        )
        loader = PromptLoader(Path(directory))
        with (
            patch.object(settings, "llm_configured", return_value=True),
            patch.object(settings, "llm_provider", "openai"),
            patch.object(security, "assert_llm_egress"),
            patch.object(security, "assert_provider_egress") as egress,
            patch.object(usage, "assert_budget"),
            patch.object(usage, "record"),
        ):
            for item in setup["tenants"]:
                token = current_client_id.set(item["scope"])
                try:
                    assert (
                        loader.call("fixture_summary", raise_errors=True)
                        == "Synthetic private answer"
                    )
                finally:
                    current_client_id.reset(token)
            assert egress.call_count == len(setup["tenants"])
        counters = dispatcher_monitoring.registry().close()
        assert all(
            row["flushed"] and not row["failed"] and not row["dropped"] for row in counters.values()
        )
        with patch.dict(os.environ, {}, clear=False):
            dispatcher_monitoring.registry.cache_clear()
            os.environ.pop("AGENTDATA_DISPATCHER_BINDINGS")
            sentinel = object()
            assert (
                dispatcher_monitoring.complete(lambda *args: sentinel, "openai", "", "", "", 1)
                is sentinel
            )
    print("Actual AgentData discovery, three analytics questions and gateway prompt calls passed.")


if __name__ == "__main__":
    main()

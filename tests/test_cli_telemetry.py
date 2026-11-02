"""CLI fixtures use per-call evidence, preserve unknowns and never persist log bodies."""

import copy
import time

from test_telemetry import attribute


def log(name, **values):
    """Represent the scalar wire shapes emitted by CLI OTLP exporters."""
    return {
        "timeUnixNano": str(time.time_ns()),
        "body": {"stringValue": "private body"},
        "attributes": [
            attribute(key, value)
            for key, value in {
                "event.name": name,
                "model": "fixture-model",
                "user.email": "private@example.test",
                "error.message": "private exception",
                "prompt": "private prompt",
                **values,
            }.items()
        ],
    }


def body(records, **values):
    """Bind resource metadata to the fixture's actual service credential."""
    return {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        attribute(key, value)
                        for key, value in {
                            "service.name": "trader",
                            "service.version": "0.164.0",
                            "env": "test",
                            **values,
                        }.items()
                    ]
                },
                "scopeLogs": [{"logRecords": records}],
            }
        ]
    }


def send(system, payload):
    """Use the public SDK-key endpoint, including normal live scope and revocation checks."""
    return system["client"].post(
        "/api/otlp/v1/logs",
        json=payload,
        headers={"Authorization": "Bearer " + system["key"]["secret"]},
    )


def test_codex_completion_is_not_double_counted_and_unknowns_stay_unknown(system):
    payload = body(
        [
            log("codex.api_request", **{"http.response.status_code": 200, "duration_ms": "20"}),
            log("codex.sse_event", **{"event.kind": "message", "duration_ms": "1"}),
            log(
                "codex.sse_event",
                **{
                    "event.kind": "response.completed",
                    "input_token_count": "7",
                    "output_token_count": "2",
                    "conversation.id": "session-fixture",
                },
            ),
            log("codex.user_prompt"),
        ]
    )
    completed = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][2]
    completed["observedTimeUnixNano"] = completed["timeUnixNano"]
    completed["timeUnixNano"] = "0"
    assert send(system, payload).json() == {}
    assert send(system, payload).json() == {}
    rows = system["client"].get("/api/events").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["cost"] is None and row["cost_kind"] == "unknown"
    assert row["payload"]["duration_ms"] is None
    assert row["payload"]["input_tokens"] == 7 and row["payload"]["output_tokens"] == 2
    assert row["payload"]["source"] == "codex"
    assert "private" not in str(rows)
    assert system["client"].get("/api/overview").json()["counts"]["average_latency_ms"] is None


def test_claude_estimates_failures_cache_tokens_and_unsupported_shapes(system):
    payload = body(
        [
            log(
                "claude_code.api_request",
                input_tokens=7,
                output_tokens=2,
                cache_read_tokens=10,
                cache_creation_tokens=3,
                cost_usd_micros=120000,
                duration_ms=15,
            ),
            log("claude_code.api_error", status_code=429, duration_ms=1, attempt=1),
            log("claude_code.api_request", cost_usd="not a number"),
            log("codex.sse_event", **{"event.kind": "response.completed"}),
            log("other.future.usage", tokens=50),
        ]
    )
    result = send(system, payload)
    assert result.status_code == 200, result.text
    assert result.json()["partialSuccess"]["rejectedLogRecords"] == "3"
    rows = system["client"].get("/api/events").json()
    assert len(rows) == 2
    success = next(row for row in rows if row["payload"]["status"] == "success")
    assert success["cost"] == "0.12" and success["cost_kind"] == "app_estimate"
    assert success["payload"]["input_tokens"] == 20
    failure = next(row for row in rows if row["payload"]["status"] == "error")
    assert failure["cost"] is None
    assert "private" not in str(rows)
    adapters = system["client"].get("/api/coverage").json()["adapters"]
    assert adapters[0]["rejected_exports"] == 3 and adapters[0]["source"] == "otlp-logs"


def test_cli_scopes_replay_changes_and_revocation(system):
    original = log("claude_code.api_request", cost_usd="0.02", duration_ms=2)
    for scope in ({"service.name": "foreign"}, {"env": "foreign"}, {"tenant.id": "foreign"}):
        assert send(system, body([original], **scope)).status_code == 403
    assert send(system, body([original])).json() == {}
    altered = copy.deepcopy(original)
    altered["attributes"].append(attribute("input_tokens", 8))
    assert send(system, body([altered])).json()["partialSuccess"]["rejectedLogRecords"] == "1"
    system["auth"].revoke_key(system["owner"], system["key"]["id"])
    assert send(system, body([original])).status_code == 401

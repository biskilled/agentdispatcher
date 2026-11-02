"""Inspect installed Codex telemetry with a loopback-only synthetic Responses provider."""

import argparse
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from dispatcher.cli_telemetry import CLI_FIELDS, normalize_log
from dispatcher.contracts import Principal
from dispatcher.telemetry import attributes

_FIELDS = {
    "event.name",
    "event.kind",
    "model",
    "duration_ms",
    "input_token_count",
    "output_token_count",
    "cached_token_count",
    "cache_write_token_count",
    "success",
    "http.response.status_code",
    "service.name",
    "service.version",
    "deployment.environment",
    "environment",
    "env",
    "provider_name",
}


def main():
    """Run a fixture without provider spend; print only allowlisted telemetry metadata."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    args = parser.parse_args()
    records = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            """Keep request bodies and URL diagnostics out of test output."""

        def do_POST(self):
            """Serve a fixed completion or accept the synthetic CLI's OTLP JSON."""
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/v1/logs":
                records.extend(body.get("resourceLogs", []))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")
                return
            response = {
                "id": "resp_dispatcher_fixture",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "fixture-model",
                "output": [
                    {
                        "id": "msg_fixture",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "OK", "annotations": []}],
                    }
                ],
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": 2,
                    "total_tokens": 9,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in (
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": response["output"][0],
                },
                {"type": "response.completed", "response": response},
            ):
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        config = {
            "model_provider": "dispatcher_fixture",
            "model": "fixture-model",
            "model_providers.dispatcher_fixture.name": "Local fixture",
            "model_providers.dispatcher_fixture.base_url": origin + "/v1",
            "model_providers.dispatcher_fixture.env_key": "DISPATCHER_FIXTURE_KEY",
            "model_providers.dispatcher_fixture.wire_api": "responses",
            "otel.environment": "fixture",
            "otel.log_user_prompt": False,
            "otel.exporter.otlp-http.endpoint": origin + "/v1/logs",
            "otel.exporter.otlp-http.protocol": "json",
        }
        command = [
            args.codex,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
        ]
        for key, value in config.items():
            command.extend(["-c", key + "=" + json.dumps(value)])
        with tempfile.TemporaryDirectory(prefix="dispatcher-codex-fixture-") as directory:
            result = subprocess.run(
                [*command, "-C", directory, "Reply OK"],
                capture_output=True,
                env={**os.environ, "DISPATCHER_FIXTURE_KEY": "synthetic-no-provider-access"},
                timeout=60,
            )
        server.shutdown()
    print("Codex fixture exit:", result.returncode)
    normalized = []
    principal = Principal(
        tenant_id=uuid4(),
        subject_id=uuid4(),
        role="service",
        app="codex_exec",
        environment="fixture",
    )
    for resource in records:
        values = resource.get("resource", {}).get("attributes", [])
        decoded = attributes(values, CLI_FIELDS)
        print("resource fields", [item["key"] for item in values])
        print("resource", {item["key"]: item["value"] for item in values if item["key"] in _FIELDS})
        for scope in resource.get("scopeLogs", []):
            for record in scope.get("logRecords", []):
                event = normalize_log(principal, decoded, record)
                if event is not None:
                    normalized.append(event)
                print(
                    "event",
                    {
                        item["key"]: item["value"]
                        for item in record.get("attributes", [])
                        if item["key"] in _FIELDS
                    },
                    "timestamp:",
                    bool(record.get("timeUnixNano")),
                )
    if result.returncode or not records:
        raise RuntimeError("Installed Codex did not complete the synthetic telemetry fixture")
    assert len(normalized) == 1, "A single completion must not become multiple attempts"
    assert normalized[0].input_tokens == 7 and normalized[0].output_tokens == 2
    assert normalized[0].reported_cost is None and normalized[0].duration_ms is None
    print("Actual CLI records normalized: one completion, 7 input / 2 output tokens; cost unknown.")


if __name__ == "__main__":
    main()

"""The downloadable collector works without site-packages and never forwards a key on redirect."""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError

import pytest
from agentdispatcher_sdk import codexbar
from test_accounts import export


@contextmanager
def receiver(callback):
    """Expose a temporary loopback receiver without provider traffic or fixed ports."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            """Capture HTTP request semantics and return the fixture's response."""
            body = self.rfile.read(int(self.headers["Content-Length"]))
            status, headers, response = callback(self.path, self.headers, body)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            """Keep fixture HTTP logs from exposing authorization headers."""
            return

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


def test_downloadable_script_without_sdk_reaches_scoped_api(system, tmp_path):
    key = system["auth"].issue_key(system["owner"], "Standalone", "device", "test", "codexbar")
    received = []

    def receive(path, headers, body):
        assert headers["Authorization"] == "Bearer " + key["secret"]
        assert b"never-export" not in body
        result = system["client"].post(path, content=body, headers=dict(headers))
        received.append(result.status_code)
        return result.status_code, {}, result.content

    script = tmp_path / "dispatcher-account-sync.py"
    script.write_text(Path(codexbar.__file__).read_text())
    source = tmp_path / "usage.json"
    source.write_text(json.dumps([export()]))
    with receiver(receive) as base:
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(script), "--file", str(source)],
            env={**os.environ, "DISPATCHER_URL": base, "DISPATCHER_ACCOUNT_KEY": key["secret"]},
            capture_output=True,
            text=True,
            timeout=30,
        )
    assert result.returncode == 0, result.stderr
    assert "Synced 1 account snapshots" in result.stdout
    assert received == [202]
    assert len(system["client"].get("/api/accounts").json()) == 1
    assert system["client"].get("/api/overview").json()["counts"]["attempts"] == 0


def test_account_upload_refuses_redirect_without_forwarding_credentials():
    requests = []

    def redirect(path, headers, body):
        requests.append(path)
        return 307, {"Location": "/redirect-target"}, b""

    with receiver(redirect) as base:
        with pytest.raises(HTTPError) as failure:
            codexbar.upload(base + "/api/accounts/snapshots", "fixture-key", [], 5)
    assert failure.value.code == 307
    assert requests == ["/api/accounts/snapshots"]

"""Run the synthetic SDK/browser workflow without putting credentials in command arguments."""

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from demo import main as seed_demo
from dotenv import load_dotenv


def verify_worker(base: str) -> None:
    """Start/stop the independent worker and confirm the API remains available."""
    with tempfile.TemporaryDirectory(prefix="dispatcher-worker-check-") as directory:
        marker = Path(directory) / "healthy"
        environment = dict(os.environ, DISPATCHER_WORKER_HEALTH_FILE=str(marker))
        worker = subprocess.Popen([sys.executable, "-m", "dispatcher.worker"], env=environment)
        try:
            deadline = time.monotonic() + 15
            while not marker.exists():
                if worker.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Worker did not become healthy")
                time.sleep(0.1)
            subprocess.run(
                [sys.executable, "-m", "dispatcher.worker", "--health"], env=environment, check=True
            )
        finally:
            worker.terminate()
            worker.wait(timeout=10)
        httpx.get(base + "/health/ready").raise_for_status()
        print("Independent worker startup/health/shutdown verified; API remains ready.")


def main() -> None:
    """Seed the configured local instance and pass an ephemeral session only via child env."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    load_dotenv(args.env_file, override=True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        seed_demo()
    demo = json.loads(output.getvalue())
    token = parse_qs(urlsplit(demo["sign_in"]).fragment)["signin"][0]
    base = os.environ["DISPATCHER_PUBLIC_URL"]
    verify_worker(base)
    with httpx.Client(base_url=base, headers={"Origin": base}) as client:
        response = client.post("/api/auth/email/consume", json={"token": token})
        response.raise_for_status()
        environment = dict(
            os.environ,
            DISPATCHER_TEST_UI_URL=base,
            DISPATCHER_TEST_SESSION=client.cookies["dispatcher_session"],
        )
        try:
            subprocess.run(["npm", "run", "test:ui"], env=environment, check=True)
        finally:
            client.post("/api/auth/logout").raise_for_status()


if __name__ == "__main__":
    main()

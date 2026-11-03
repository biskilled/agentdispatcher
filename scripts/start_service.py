"""Start a Python service using platform-provided network configuration."""

import os
import sys


def main() -> None:
    """Require explicit service selection; runtime processes never run owner migrations."""
    service = sys.argv[1]
    if service == "api":
        args = [
            "uvicorn",
            "dispatcher.api:create_app",
            "--factory",
            "--host",
            os.environ["API_HOST"],
            "--port",
            os.environ["PORT"],
            "--no-access-log",
        ]
    elif service == "worker":
        args = ["dispatcher-worker"]
    else:
        raise SystemExit("Expected api or worker")
    os.execvp(args[0], args)


if __name__ == "__main__":
    main()

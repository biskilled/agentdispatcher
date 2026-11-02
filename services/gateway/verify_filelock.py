"""Verify the FileLock/Timeout API used by LiteLLM across two real processes."""

import subprocess
import sys
import tempfile
from pathlib import Path

from filelock import FileLock

_CONTENDER = """
import sys
from filelock import FileLock, Timeout
try:
    with FileLock(sys.argv[1], timeout=0):
        acquired = True
except Timeout:
    acquired = False
assert acquired == (sys.argv[2] == 'available')
"""


def main() -> None:
    """Prove mutual exclusion and release without relying on process timing sleeps."""
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "profile.lock")
        with FileLock(path, timeout=0):
            subprocess.run([sys.executable, "-c", _CONTENDER, path, "locked"], check=True)
        subprocess.run([sys.executable, "-c", _CONTENDER, path, "available"], check=True)
    print("Gateway FileLock/Timeout cross-process compatibility passed.")


if __name__ == "__main__":
    main()

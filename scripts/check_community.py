"""Reject enterprise imports, callbacks and license activation in shipped integration code."""

import re
from pathlib import Path

_ENTERPRISE_REFERENCE = re.compile(
    r"\blitellm(?:[_./]enterprise|[./]proxy[./]enterprise)\b|\bLITELLM_LICENSE(?:_PATH)?\b",
    re.IGNORECASE,
)
_SOURCE_SUFFIXES = {".py", ".yaml", ".yml", ".ts", ".tsx"}


def check_source(path: Path, source: str) -> None:
    """Reject explicit enterprise references; this is not a runtime dependency audit."""
    if _ENTERPRISE_REFERENCE.search(source):
        raise RuntimeError(f"Enterprise integration requires review: {path}")


def main() -> None:
    """Check owned application/configuration sources, excluding upstream image internals."""
    root = Path(__file__).resolve().parents[1]
    for directory in ("packages", "services", "integrations"):
        for path in (root / directory).rglob("*"):
            if path.is_file() and path.suffix in _SOURCE_SUFFIXES:
                check_source(path.relative_to(root), path.read_text())
    check_source(Path("compose.yaml"), (root / "compose.yaml").read_text())
    print("Community integration checks passed.")


if __name__ == "__main__":
    main()

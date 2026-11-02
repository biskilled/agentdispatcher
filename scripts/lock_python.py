"""Resolve the installed runtime closure into reproducible version pins."""

import argparse
import tomllib
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def main() -> None:
    """Write runtime pins only; run in the verified development environment."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    dependencies = (
        project["optional-dependencies"]["dev"] + ["setuptools"]
        if args.dev
        else project["dependencies"]
    )
    pending = [Requirement(value) for value in dependencies]
    resolved, visited = {}, set()
    while pending:
        requirement = pending.pop()
        key = (canonicalize_name(requirement.name), tuple(sorted(requirement.extras)))
        if key in visited:
            continue
        visited.add(key)
        package = distribution(requirement.name)
        resolved[key[0]] = package.version
        for raw in package.requires or []:
            dependency = Requirement(raw)
            if dependency.marker is None or any(
                dependency.marker.evaluate({"extra": extra})
                for extra in (requirement.extras or {""})
            ):
                pending.append(dependency)
    (root / ("requirements-dev.lock" if args.dev else "requirements.lock")).write_text(
        "# Installed closure verified by scripts/lock_python.py; regenerate after upgrades.\n"
        + "\n".join(f"{name}=={version}" for name, version in sorted(resolved.items()))
        + "\n"
    )


if __name__ == "__main__":
    main()

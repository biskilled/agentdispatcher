"""Apply an explicit, versioned dependency-only fork to the installed gateway distribution."""

import base64
import csv
import hashlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path


def patch_metadata(source: str, config: dict) -> str:
    """Fail closed if the upstream version or dependency contract has changed."""
    version = f"Version: {config['upstream_version']}"
    if source.splitlines().count(version) != 1:
        raise ValueError("Unexpected upstream version; review the dependency backport")
    pattern = rf"^Requires-Dist: {re.escape(config['dependency'])}\s*(.*)$"
    matches = list(re.finditer(pattern, source, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError("Expected exactly one upstream dependency declaration")
    match = matches[0]
    specifiers = match.group(1).strip().strip("()").replace(" ", "").split(",")
    if sorted(specifiers) != sorted(config["expected_specifiers"]):
        raise ValueError("Unexpected upstream dependency constraint; review required")
    patched = (
        source[: match.start()] + f"Requires-Dist: {config['replacement']}" + source[match.end() :]
    )
    return patched.replace(version + "\n", f"Version: {config['local_version']}\n", 1)


def apply_backport(metadata_path: Path, config: dict) -> None:
    """Preserve package files/licenses and update the local version and RECORD checksums."""
    original = metadata_path.parent
    destination = original.with_name(
        f"{config['distribution']}-{config['local_version']}.dist-info"
    )
    if destination.exists():
        raise ValueError("Backport destination already exists")
    patched = patch_metadata(metadata_path.read_text(), config)
    with (original / "RECORD").open(newline="") as source:
        records = list(csv.reader(source))
    original.rename(destination)
    (destination / "METADATA").write_text(patched)
    (destination / "DISPATCHER-BACKPORT.json").write_text(json.dumps(config, indent=2) + "\n")
    changed = {"METADATA", "DISPATCHER-BACKPORT.json"}
    updated = []
    for row in records:
        path, digest, size = row
        if path.startswith(original.name + "/"):
            path = destination.name + path[len(original.name) :]
        if path in {f"{destination.name}/{name}" for name in changed}:
            continue
        updated.append([path, digest, size])
    for name in sorted(changed):
        data = (destination / name).read_bytes()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        updated.append([f"{destination.name}/{name}", f"sha256={digest}", str(len(data))])
    with (destination / "RECORD").open("w", newline="") as output:
        csv.writer(output).writerows(updated)


def main() -> None:
    """Backport only on the supported gateway Python and print auditable version provenance."""
    if sys.version_info < (3, 11):
        raise SystemExit("This dependency backport requires Python 3.11+")
    config = json.loads(Path(sys.argv[1]).read_text())
    distribution = importlib.metadata.distribution(config["distribution"])
    paths = [
        path for path in distribution.files if path.name == "METADATA" and ".dist-info" in str(path)
    ]
    if len(paths) != 1:
        raise SystemExit("Expected one installed distribution metadata file")
    apply_backport(Path(distribution.locate_file(paths[0])), config)
    print(
        f"Applied explicit local distribution: {config['distribution']} {config['local_version']}"
    )


if __name__ == "__main__":
    main()

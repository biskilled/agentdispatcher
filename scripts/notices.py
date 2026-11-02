"""Generate runtime attribution from installed packages and reject prohibited licenses."""

import argparse
import json
from importlib.metadata import distribution
from pathlib import Path


def checked_license(name: str, license_name: str) -> str:
    """Fail on missing or explicitly prohibited licenses rather than guessing terms."""
    if not license_name or any(
        word in license_name.upper()
        for word in ("AGPL", "PROPRIETARY", "COMMERCIAL", "BUSL", "SSPL", "UNKNOWN")
    ):
        raise RuntimeError(f"Review required for {name}: {license_name or 'unknown license'}")
    return license_name


def python_notices(root: Path, lock_name="requirements.lock") -> list[dict]:
    """Read the pinned runtime closure and all bundled distribution license files."""
    notices = []
    for line in (root / lock_name).read_text().splitlines():
        if line.startswith("#") or not line:
            continue
        name, version = line.split("==")
        package = distribution(name)
        if package.version != version:
            raise RuntimeError(f"Installed {name} does not match requirements.lock")
        metadata = package.metadata
        license_name = metadata.get("License-Expression") or metadata.get("License", "")
        if not license_name:
            license_name = "; ".join(
                value.split(" :: ")[-1]
                for value in metadata.get_all("Classifier", [])
                if value.startswith("License ::")
            )
        texts = []
        for file in package.files or []:
            if "license" in str(file).lower() or "copying" in file.name.lower():
                path = package.locate_file(file)
                if path.is_file() and path.suffix not in (".py", ".pyc"):
                    texts.append({"file": str(file), "text": path.read_text(errors="replace")})
        urls = metadata.get_all("Project-URL", [])
        notices.append(
            {
                "name": name,
                "version": version,
                "license": checked_license(name, license_name),
                "source": metadata.get("Home-page") or (urls[0].split(", ")[-1] if urls else ""),
                "ecosystem": "Python",
                "texts": texts,
            }
        )
    return notices


def node_notices(root: Path) -> list[dict]:
    """Traverse shipped JavaScript packages only, preserving their original license text."""
    pending = list(json.loads((root / "package.json").read_text())["dependencies"])
    seen, notices = set(), []
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        directory = root / "node_modules" / name
        metadata = json.loads((directory / "package.json").read_text())
        texts = [
            {"file": file.name, "text": file.read_text(errors="replace")}
            for file in directory.iterdir()
            if file.is_file() and file.name.lower().startswith(("license", "copying", "notice"))
        ]
        repository = metadata.get("repository", {})
        source = repository.get("url", "") if isinstance(repository, dict) else repository
        notices.append(
            {
                "name": name,
                "version": metadata["version"],
                "license": checked_license(name, metadata.get("license", "")),
                "source": metadata.get("homepage") or source,
                "ecosystem": "JavaScript",
                "texts": texts,
            }
        )
        pending.extend(metadata.get("dependencies", {}))
    return notices


def main() -> None:
    """Produce the single notice artifact used by the source distribution and UI."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-only-root", type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    root = args.python_only_root or Path(__file__).resolve().parents[1]
    if args.development:
        notices = python_notices(root, "requirements-dev.lock")
        lock = json.loads((root / "package-lock.json").read_text())
        for path, item in lock["packages"].items():
            if not path:
                continue
            name = path.split("node_modules/")[-1]
            notices.append(
                {
                    "name": name,
                    "version": item["version"],
                    "license": checked_license(name, item.get("license", "")),
                    "source": f"https://www.npmjs.com/package/{name}/v/{item['version']}",
                    "ecosystem": "JavaScript build tools",
                    "optional": item.get("optional", False),
                }
            )
        (root / "third_party/development.json").write_text(json.dumps(notices, indent=2) + "\n")
        print(
            f"Recorded {len(notices)} development/optional package attributions from version locks."
        )
        return
    notices = python_notices(root)
    if not args.python_only_root:
        notices.extend(node_notices(root))
        optional = root / "services/mcp/third_party/notices.json"
        if optional.exists():
            notices.extend(json.loads(optional.read_text()))
    notices = sorted(
        {(item["name"], item["version"], item["ecosystem"]): item for item in notices}.values(),
        key=lambda item: (item["name"], item["version"]),
    )
    missing = [item["name"] for item in notices if not item["texts"]]
    if missing:
        raise RuntimeError(f"License text missing for {missing}; review distribution files")
    destination = root / "third_party"
    destination.mkdir(exist_ok=True)
    (destination / "notices.json").write_text(json.dumps(notices, indent=2) + "\n")
    print(f"Recorded license texts and attribution for {len(notices)} runtime packages.")


if __name__ == "__main__":
    main()

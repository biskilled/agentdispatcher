"""Build the macOS collector with pinned upstream readers and its own Python runtime."""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import sysconfig
import tarfile
from importlib.metadata import distribution
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZIP_DEFLATED, ZipFile


def fetch_readers(manifest, cache, destination):
    """Verify upstream digests before unpacking complete readers and their resources/notices."""
    for arch, item in manifest["artifacts"].items():
        archive = cache / f"codexbar-{manifest['version']}-{arch}.tar.gz"
        if not archive.exists():
            with urlopen(item["url"], timeout=60) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        with archive.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Reader checksum mismatch: {arch}")
        target = destination / arch
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as source:
            source.extractall(target, filter="data")
        if not (target / manifest["executable"]).is_file():
            raise ValueError(f"Missing reader executable: {arch}")


def main():
    """Emit one ZIP; signing/notarization requires an operator-supplied Apple identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--signing-identity")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("This universal macOS build requires macOS and a universal Python runtime")
    root = args.root.resolve()
    output = (args.output or root / "dist" / "collector").resolve()
    work = root / "build" / "collector"
    cache, readers, notices = work / "cache", work / "readers", work / "licenses"
    for directory in (cache, notices, output):
        directory.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "packaging/collector/upstream.json"
    manifest = json.loads(manifest_path.read_text())
    fetch_readers(manifest, cache, readers)
    shutil.copyfile(root / "LICENSE", notices / "AgentDispatcher-LICENSE.txt")
    shutil.copyfile(
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", notices / "Python-LICENSE.txt"
    )
    integrations = json.loads((root / "third_party/integrations.json").read_text())
    codexbar = next(item for item in integrations if item["name"] == "CodexBar")
    (notices / "CodexBar-LICENSE.txt").write_text(codexbar["texts"][0]["text"])
    package = distribution("pyinstaller")
    for item in package.files or []:
        if item.name == "COPYING.txt":
            shutil.copyfile(package.locate_file(item), notices / "PyInstaller-COPYING.txt")
    # The original upstream notices travel with each unmodified reader.
    (work / "collector-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--target-arch",
        "universal2",
        "--name",
        "AgentDispatcherCollector",
        "--distpath",
        str(output),
        "--workpath",
        str(work / "pyinstaller"),
        "--specpath",
        str(work),
        "--add-data",
        f"{readers}:readers",
        "--add-data",
        f"{notices}:licenses",
        "--add-data",
        f"{work / 'collector-manifest.json'}:.",
    ]
    if args.signing_identity:
        command += ["--codesign-identity", args.signing_identity]
    command.append(str(root / "packages/sdk/src/agentdispatcher_sdk/codexbar.py"))
    subprocess.run(command, check=True)
    binary = output / "AgentDispatcherCollector"
    bundle = output / "AgentDispatcherCollector-macos-universal.zip"
    with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(binary, binary.name)
        archive.write(root / "packaging/collector/README.md", "README.md")
        archive.write(manifest_path, "upstream.json")
        for directory in (notices, readers):
            for path in directory.rglob("*"):
                if path.is_file() and (directory == notices or path.name == "THIRD_PARTY_NOTICES"):
                    archive.write(path, str(Path("licenses") / path.relative_to(work)))
    with bundle.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    bundle.with_suffix(bundle.suffix + ".sha256").write_text(f"{digest}  {bundle.name}\n")
    print(json.dumps({"artifact": str(bundle), "sha256": digest, "reader": manifest["version"]}))


if __name__ == "__main__":
    main()

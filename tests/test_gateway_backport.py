"""The dependency fork must reject upstream drift and retain valid installed-file records."""

import base64
import csv
import errno
import hashlib
import importlib.util
import json
import runpy
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[1] / "services/gateway"
_SPEC = importlib.util.spec_from_file_location(
    "gateway_backport", _ROOT / "apply_dependency_backport.py"
)
_BACKPORT = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_BACKPORT)
_CONFIG = json.loads((_ROOT / "dependency-backport.json").read_text())
_METADATA = (
    "Metadata-Version: 2.1\nName: litellm\nVersion: 1.106.6\n"
    "Requires-Dist: filelock (<4.0,>=3.16.1)\n"
    "Requires-Dist: httpx\n\nOriginal description\n"
)


@pytest.mark.parametrize("overlay", [False, True])
def test_backport_preserves_code_and_licenses_and_rehashes_changed_metadata(
    tmp_path, monkeypatch, overlay
):
    if overlay:

        def cross_layer_rename(*args):
            raise OSError(errno.EXDEV, "Invalid cross-device link")

        monkeypatch.setattr(_BACKPORT.shutil.os, "rename", cross_layer_rename)
    original = tmp_path / "litellm-1.106.6.dist-info"
    original.mkdir()
    (original / "METADATA").write_text(_METADATA)
    (original / "LICENSE").write_text("Original upstream license\n")
    (original / "RECORD").write_text(
        "litellm-1.106.6.dist-info/METADATA,,\nlitellm-1.106.6.dist-info/RECORD,,\nlitellm-1.106.6.dist-info/LICENSE,,\nlitellm/__init__.py,sha256=unchanged,42\n"
    )
    _BACKPORT.apply_backport(original / "METADATA", _CONFIG)
    target = tmp_path / "litellm-1.106.6+dispatcher.1.dist-info"
    assert not original.exists()
    metadata = (target / "METADATA").read_text()
    assert "Version: 1.106.6+dispatcher.1\n" in metadata
    assert "Requires-Dist: filelock>=4.2.1,<5.0\n" in metadata
    assert "Requires-Dist: httpx\n\nOriginal description\n" in metadata
    assert (target / "LICENSE").read_text() == "Original upstream license\n"
    with (target / "RECORD").open() as source:
        records = {row[0]: row[1:] for row in csv.reader(source)}
    assert records["litellm/__init__.py"] == ["sha256=unchanged", "42"]
    assert records[f"{target.name}/RECORD"] == ["", ""]
    for name in ("METADATA", "DISPATCHER-BACKPORT.json"):
        data = (target / name).read_bytes()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        assert records[f"{target.name}/{name}"] == [f"sha256={digest}", str(len(data))]


@pytest.mark.parametrize(
    "source",
    [
        _METADATA.replace("1.106.6", "1.106.7"),
        _METADATA.replace("<4.0", "<5.0"),
        _METADATA.replace("Requires-Dist: filelock", "Requires-Dist: another-package"),
        _METADATA + "Requires-Dist: filelock (<4.0,>=3.16.1)\n",
    ],
)
def test_upstream_drift_aborts_before_mutation(tmp_path, source):
    original = tmp_path / "litellm-1.106.6.dist-info"
    original.mkdir()
    metadata = original / "METADATA"
    metadata.write_text(source)
    with pytest.raises(ValueError):
        _BACKPORT.apply_backport(metadata, _CONFIG)
    assert metadata.read_text() == source


def test_advisory_inventory_checks_original_upstream_code_despite_local_version(tmp_path):
    audit = runpy.run_path(str(_ROOT.parents[1] / "scripts/audit_dependencies.py"))
    lock = tmp_path / "requirements.lock"
    lock.write_text("filelock==4.2.4\n")
    entries = audit["packages"]([lock], [_ROOT / "dependency-backport.json"])
    assert entries == [("filelock", "4.2.4"), ("litellm", "1.106.6")]

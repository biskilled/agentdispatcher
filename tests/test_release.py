"""License gates must reject missing or prohibited declarations before packaging artifacts."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "notices", Path(__file__).parents[1] / "scripts/notices.py"
)
_notices = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_notices)


@pytest.mark.parametrize(
    "license_name", ["", "UNKNOWN", "AGPL-3.0-only", "BUSL-1.1", "Commercial", "SSPL-1.0"]
)
def test_prohibited_or_unresolved_licenses_fail_closed(license_name):
    with pytest.raises(RuntimeError, match="Review required"):
        _notices.checked_license("fixture", license_name)


def test_separate_unmodified_lgpl_dependency_retains_its_license():
    assert _notices.checked_license("fixture", "LGPL-3.0-only") == "LGPL-3.0-only"

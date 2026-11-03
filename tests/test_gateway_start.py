"""A credential-free deployment must preserve gateway authorization configuration."""

import runpy
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).parents[1] / "services/gateway"
_CONFIGURE = runpy.run_path(str(_ROOT / "start.py"))["configure"]


def test_unconfigured_gateway_has_no_provider_routes_and_keeps_security():
    source = yaml.safe_load((_ROOT / "config.yaml").read_text())
    result = _CONFIGURE(source, "", "")
    assert result["model_list"] == []
    assert result["general_settings"] == source["general_settings"]
    assert result["litellm_settings"] == source["litellm_settings"]
    assert source["model_list"]
    assert _CONFIGURE(source, "provider/model", "secret") == source


@pytest.mark.parametrize("model,key", [("provider/model", ""), ("", "secret")])
def test_partial_credentials_fail_closed(model, key):
    with pytest.raises(ValueError, match="Configure both"):
        _CONFIGURE({}, model, key)

"""Start the hosted gateway with no provider routes until credentials are configured."""

import os
import tempfile
from pathlib import Path

import yaml


def configure(source: dict, model: str, key: str) -> dict:
    """Keep shared security settings and reject partially configured provider credentials."""
    uses_template = any(
        entry.get("litellm_params", {}).get("model") == "os.environ/LLM_PROVIDER_MODEL"
        for entry in source.get("model_list", [])
    )
    if not uses_template:
        return dict(source)
    if bool(model) != bool(key):
        raise ValueError("Configure both LLM_PROVIDER_MODEL and LLM_API_KEY, or leave both empty")
    result = dict(source)
    if not model:
        result["model_list"] = [
            entry
            for entry in source.get("model_list", [])
            if entry.get("litellm_params", {}).get("model") != "os.environ/LLM_PROVIDER_MODEL"
        ]
    return result


def main() -> None:
    """Render metadata-only configuration and run the upstream launcher as the main process."""
    source = Path(os.environ["GATEWAY_CONFIG_PATH"])
    config = configure(
        yaml.safe_load(source.read_text()),
        os.environ.get("LLM_PROVIDER_MODEL", ""),
        os.environ.get("LLM_API_KEY", ""),
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as output:
        yaml.safe_dump(config, output)
        destination = output.name
    launcher = os.environ["GATEWAY_LAUNCHER"]
    os.execv(
        launcher,
        [
            launcher,
            "--config",
            destination,
            "--host",
            os.environ["GATEWAY_HOST"],
            "--port",
            os.environ["PORT"],
        ],
    )


if __name__ == "__main__":
    main()

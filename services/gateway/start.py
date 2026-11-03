"""Start the hosted gateway with no provider routes until credentials are configured."""

import os
import tempfile
from pathlib import Path

import yaml


def configure(source: dict, model: str, key: str) -> dict:
    """Keep shared security settings and reject partially configured provider credentials."""
    if bool(model) != bool(key):
        raise ValueError("Configure both LLM_PROVIDER_MODEL and LLM_API_KEY, or leave both empty")
    result = dict(source)
    if not model:
        result["model_list"] = []
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

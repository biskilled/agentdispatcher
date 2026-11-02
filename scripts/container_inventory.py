"""Resolve one Compose image without printing the rendered configuration's private environment."""

import argparse
import json
import os
import subprocess
from pathlib import Path

_COMPOSE = [
    "docker",
    "compose",
    "--profile",
    "gateway",
    "--profile",
    "telemetry",
    "--profile",
    "mcp",
    "--profile",
    "recovery",
]


def main():
    """Build or pull one service and publish only its image reference to the CI step output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "service", choices=("api", "ui", "mcp", "gateway", "collector", "db", "recovery")
    )
    parser.add_argument("--resolve-only", action="store_true")
    args = parser.parse_args()
    config = json.loads(subprocess.check_output([*_COMPOSE, "config", "--format", "json"]))
    service = config["services"][args.service]
    if not args.resolve_only and "build" in service:
        subprocess.run([*_COMPOSE, "build", args.service], check=True)
    elif not args.resolve_only:
        subprocess.run([*_COMPOSE, "pull", args.service], check=True)
    image = service.get("image") or f"{config['name']}-{args.service}"
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"image={image}\n")
        base = service.get("build", {}).get("args", {}).get("LITELLM_IMAGE", image)
        output.write(f"base_image={base}\n")


if __name__ == "__main__":
    main()

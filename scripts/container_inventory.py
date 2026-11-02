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
    args = parser.parse_args()
    config = json.loads(subprocess.check_output([*_COMPOSE, "config", "--format", "json"]))
    service = config["services"][args.service]
    if "build" in service:
        subprocess.run([*_COMPOSE, "build", args.service], check=True)
    else:
        subprocess.run([*_COMPOSE, "pull", args.service], check=True)
    image = service.get("image") or f"{config['name']}-{args.service}"
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"image={image}\n")


if __name__ == "__main__":
    main()

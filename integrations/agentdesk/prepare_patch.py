"""Prepare a minimal identity-endpoint patch against an explicitly selected AgentDesk checkout."""

import argparse
import difflib
from pathlib import Path


def main():
    """Write a reviewable patch without editing the other repository or its working changes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--agentdesk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    relative = "backend/routers/route_auth.py"
    original = (args.agentdesk / relative).read_text()
    if "route_dispatcher_identity" in original:
        raise SystemExit("AgentDesk identity integration is already installed")
    addition = (
        "\n\n# Explicitly linked external apps need live, tenant-aware identity proof.\n"
        "from routers.route_dispatcher_identity import router as dispatcher_identity_router\n"
        "router.include_router(dispatcher_identity_router)\n"
    )
    changes = list(
        difflib.unified_diff(
            original.splitlines(True),
            (original + addition).splitlines(True),
            fromfile="a/" + relative,
            tofile="b/" + relative,
        )
    )
    route = "backend/routers/route_dispatcher_identity.py"
    source = Path(__file__).with_name("route_dispatcher_identity.py").read_text()
    changes.extend(
        difflib.unified_diff([], source.splitlines(True), fromfile="/dev/null", tofile="b/" + route)
    )
    args.output.write_text("".join(changes))


if __name__ == "__main__":
    main()

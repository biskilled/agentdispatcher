"""Check pinned Python runtime packages against OSV without installing another audit dependency."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx


def packages(paths):
    """Read exact version locks and deduplicate shared packages across isolated services."""
    result = set()
    for path in paths:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, version = line.split("==")
            result.add((name.lower().replace("_", "-"), version))
    return sorted(result)


def audit(entries, endpoint, timeout):
    """Require complete successful advisory responses; unavailable data cannot pass a release."""
    pending = [
        {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
        for name, version in entries
    ]
    findings = []
    with httpx.Client(timeout=timeout) as client:
        while pending:
            response = client.post(endpoint, json={"queries": pending})
            response.raise_for_status()
            results = response.json()["results"]
            if len(results) != len(pending):
                raise ValueError("Incomplete advisory response")
            following = []
            for query, result in zip(pending, results, strict=True):
                if result.get("error"):
                    raise ValueError("Advisory service could not evaluate a locked package")
                for vulnerability in result.get("vulns", []):
                    findings.append(
                        {
                            "name": query["package"]["name"],
                            "version": query["version"],
                            "advisory": vulnerability["id"],
                        }
                    )
                if token := result.get("next_page_token"):
                    if token == query.get("page_token"):
                        raise ValueError("Advisory pagination did not advance")
                    following.append({**query, "page_token": token})
            pending = following
    return findings


def main():
    """Write timestamped evidence and fail on any advisory affecting a pinned runtime package."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("locks", type=Path, nargs="+")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    entries = packages(args.locks)
    findings = audit(entries, args.endpoint, args.timeout)
    args.output.write_text(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "packages": len(entries),
                "source": args.endpoint,
                "findings": findings,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Advisory check: {len(entries)} locked packages; {len(findings)} findings.")
    for finding in findings:
        print(f"{finding['name']} {finding['version']}: {finding['advisory']}")
    raise SystemExit(bool(findings))


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: Apache-2.0
"""Sync account measurements using Python's standard library and the local CodexBar CLI."""

import argparse
import getpass
import json
import math
import os
import platform
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def configuration_path():
    """Allow managed deployments to choose the collector's private configuration location."""
    return Path(
        os.getenv(
            "DISPATCHER_COLLECTOR_CONFIG", Path.home() / ".agentdispatcher" / "collector.json"
        )
    )


def validate_url(base):
    """Reject credentials and ambiguous destinations before sending the sync key."""
    address = urlsplit(base)
    if (
        address.scheme not in {"https", "http"}
        or not address.hostname
        or address.username
        or address.password
        or address.query
        or address.fragment
    ):
        raise ValueError("Enter the HTTP(S) app URL without credentials, query or fragment")


def configure(path):
    """Save a user-entered URL/key in an owner-only file; never echo the key."""
    base = input("Dispatcher app URL: ").strip().rstrip("/")
    validate_url(base)
    key = getpass.getpass("CLI account sync key: ").strip()
    if not key:
        raise ValueError("A sync key is required")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        json.dump({"url": base, "key": key}, output)
    try:
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print("Configuration saved. Run this collector with --interval 300 to sync periodically.")


def reader_executable():
    """Use the bundled reader, with an explicit override for developers and managed hosts."""
    if os.getenv("CODEXBAR_BIN"):
        return os.environ["CODEXBAR_BIN"]
    root = Path(__file__).resolve().parent
    manifest = root / "collector-manifest.json"
    if manifest.exists():
        metadata = json.loads(manifest.read_text())
        return str(root / "readers" / platform.machine() / metadata["executable"])
    return "codexbar"


class NoRedirect(HTTPRedirectHandler):
    """Keep the sync credential on the configured origin, even if a server redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject redirects instead of forwarding account data and bearer credentials."""
        return None


def upload(endpoint, credential, snapshots, timeout):
    """Send sanitized snapshots without requiring the Dispatcher SDK or third-party packages."""
    request = Request(
        endpoint,
        data=json.dumps({"snapshots": snapshots}, allow_nan=False).encode(),
        headers={"Authorization": "Bearer " + credential, "Content-Type": "application/json"},
        method="POST",
    )
    with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Dispatcher rejected account sync (HTTP {response.status})")


def _text(value, limit=200):
    return value[:limit] if isinstance(value, str) else None


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def _object(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Expected a CodexBar JSON object")
    return value


def _items(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected a CodexBar JSON list")
    return value


def normalize(payload, collected_at=None):
    """Project generic CodexBar usage JSON onto a bounded, credential-free snapshot contract."""
    if not isinstance(payload, list) or len(payload) > 200:
        raise ValueError("Expected a CodexBar usage JSON array with at most 200 accounts")
    collected_at = collected_at or datetime.now(UTC).isoformat()
    results = []
    for row in payload:
        if not isinstance(row, dict) or not isinstance(row.get("provider"), str):
            raise ValueError("Each CodexBar account must identify its provider")
        usage, credits = _object(row.get("usage")), _object(row.get("credits"))
        labels = _object(row.get("rateWindowLabels"))
        windows = []
        candidates = [
            (labels.get(key) or key, usage.get(key)) for key in ("primary", "secondary", "tertiary")
        ]
        candidates += [
            (
                item.get("title") or "Additional limit",
                {**_object(item.get("window")), "usedPercent": None}
                if item.get("usageKnown") is False
                else item.get("window"),
            )
            for item in _items(usage.get("extraRateWindows"))
            if isinstance(item, dict)
        ]
        for label, window in candidates:
            if not isinstance(window, dict) or window.get("isSyntheticPlaceholder"):
                continue
            windows.append(
                {
                    "label": _text(window.get("title") or label),
                    "used_percent": _number(window.get("usedPercent")),
                    "window_minutes": _number(window.get("windowMinutes")),
                    "resets_at": window.get("resetsAt"),
                    "reset_description": _text(window.get("resetDescription")),
                    "quota_limit": _number(window.get("quotaLimit")),
                    "quota_unit": _text(window.get("quotaUnit")),
                }
            )
        details = []
        for section in _items(usage.get("details")):
            if not isinstance(section, dict):
                continue
            for detail in _items(section.get("rows")):
                if isinstance(detail, dict) and isinstance(detail.get("label"), str):
                    details.append(
                        {
                            "label": _text(detail["label"]),
                            "value": _text(detail.get("value")),
                            "secondary_value": _text(detail.get("secondaryValue")),
                        }
                    )
        if len(windows) > 50 or len(details) > 200:
            raise ValueError("CodexBar snapshot exceeds the supported display limits")
        identity = _object(usage.get("identity"))
        account = (
            row.get("account")
            or usage.get("accountEmail")
            or identity.get("accountEmail")
            or "Default account"
        )
        if not isinstance(account, str) or len(account) > 200:
            raise ValueError("Invalid CodexBar account label")
        spend = usage.get("providerCost")
        results.append(
            {
                "provider": row["provider"],
                "account": account,
                "source": _text(row.get("source")) or "unknown",
                "version": _text(row.get("version")),
                "collected_at": collected_at,
                "observed_at": usage.get("updatedAt") or credits.get("updatedAt"),
                "status": "error"
                if row.get("error")
                else "ready"
                if usage or credits
                else "unavailable",
                "windows": windows,
                "credits_remaining": _number(credits.get("remaining"))
                if credits.get("balanceReadSucceeded", True)
                else None,
                "details": details,
                "spend": {
                    "used": _number(spend.get("used")),
                    "limit": _number(spend.get("limit")),
                    "unit": _text(spend.get("currencyCode")),
                    "period": _text(spend.get("period")),
                    "balance": _number(spend.get("balance")),
                    "personal_used": _number(spend.get("personalUsed")),
                    "resets_at": spend.get("resetsAt"),
                    "observed_at": spend.get("updatedAt"),
                }
                if isinstance(spend, dict)
                else None,
            }
        )
    return results


def collect(executable, provider, timeout, max_bytes, file=None, all_accounts=False):
    """Read bounded JSON from a file or the installed CLI; retain partial-provider results."""
    if file:
        path = Path(file)
        if path.stat().st_size > max_bytes:
            raise ValueError("CodexBar export is too large")
        return normalize(json.loads(path.read_text())), False
    command = [executable, "usage", "--format", "json"]
    if provider:
        command.extend(["--provider", provider])
    if all_accounts:
        command.append("--all-accounts")
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.DEVNULL, timeout=timeout)
        if output.tell() > max_bytes:
            raise ValueError("CodexBar export is too large")
        output.seek(0)
        snapshots = normalize(json.load(output))
    return snapshots, result.returncode != 0


def main():
    """Send one account snapshot batch, or poll at an explicitly requested interval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configure", action="store_true", help="Save the Dispatcher URL and sync key"
    )
    parser.add_argument("--config", type=Path, default=configuration_path())
    parser.add_argument(
        "--reader", nargs=argparse.REMAINDER, help="Run the included account reader's own commands"
    )
    parser.add_argument("--file", help="Read an existing CodexBar usage JSON export")
    parser.add_argument("--provider", help="CodexBar provider ID; omitted uses enabled providers")
    parser.add_argument(
        "--all-accounts", action="store_true", help="All configured accounts for one provider"
    )
    parser.add_argument(
        "--interval", type=float, default=0, help="Repeat every N seconds; zero runs once"
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--max-bytes", type=int, default=1048576)
    args = parser.parse_args()
    if args.configure:
        try:
            configure(args.config)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        return
    if args.reader is not None:
        try:
            raise SystemExit(subprocess.call([reader_executable(), *args.reader]))
        except OSError:
            parser.error("Could not start the account reader; check the collector installation")
    if (
        not math.isfinite(args.interval)
        or not math.isfinite(args.timeout)
        or args.interval < 0
        or args.timeout <= 0
        or args.max_bytes <= 0
    ):
        parser.error("Interval must be nonnegative; timeout and max-bytes must be positive")
    if args.all_accounts and (not args.provider or args.provider == "all"):
        parser.error("--all-accounts requires one --provider")
    config = {}
    if args.config.exists():
        try:
            config = _object(json.loads(args.config.read_text()))
        except (OSError, ValueError):
            parser.error("Could not read collector configuration; run --configure again")
    base = os.getenv("DISPATCHER_URL") or config.get("url")
    credential = os.getenv("DISPATCHER_ACCOUNT_KEY") or config.get("key")
    if not base or not credential:
        parser.error("Run --configure, or set DISPATCHER_URL and DISPATCHER_ACCOUNT_KEY")
    if not isinstance(base, str) or not isinstance(credential, str):
        parser.error("Invalid collector configuration; run --configure again")
    try:
        validate_url(base)
    except ValueError as error:
        parser.error(str(error))
    endpoint = base.rstrip("/") + "/api/accounts/snapshots"
    while True:
        try:
            snapshots, partial = collect(
                reader_executable(),
                args.provider,
                args.timeout,
                args.max_bytes,
                args.file,
                args.all_accounts,
            )
            upload(endpoint, credential, snapshots, args.timeout)
            print(
                f"Synced {len(snapshots)} account snapshots"
                + ("; some providers failed" if partial else ""),
                flush=True,
            )
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.TimeoutExpired,
            HTTPException,
        ) as error:
            # Provider stderr may contain session data; never forward it or print raw HTTP bodies.
            print(
                f"Account sync failed: {type(error).__name__}. "
                "Check local CodexBar setup and Dispatcher access.",
                flush=True,
            )
            if not args.interval:
                raise SystemExit(1) from None
        if not args.interval:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

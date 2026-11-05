"""Real tenant isolation and the upstream CodexBar JSON contract without provider traffic."""

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from agentdispatcher_sdk import codexbar
from agentdispatcher_sdk.codexbar import collect, normalize
from dispatcher.accounts import AccountBatch, Accounts
from dispatcher.membership import MembershipService
from dispatcher.reporting import Reporter
from dispatcher.retention import Retention
from dispatcher.tenant_admin import delete_tenant
from test_access import invite_user
from test_integration import event, ingest

_SQL_AGE_ACCOUNT = "UPDATE mem_account_snapshots SET received_at=%s WHERE tenant_id=%s"


def export(provider="copilot", **extra):
    """Match CodexBar ProviderPayload/UsageSnapshot, including unknown and placeholder lanes."""
    return {
        "provider": provider,
        "source": "oauth",
        "account": "Developer account",
        "usage": {
            "updatedAt": datetime.now(UTC).isoformat(),
            "primary": {"usedPercent": 25, "resetsAt": "2030-01-01T00:00:00Z"},
            "secondary": {"usedPercent": 0, "isSyntheticPlaceholder": True},
            "extraRateWindows": [
                {"title": "Model-specific", "usageKnown": False, "window": {"usedPercent": 100}}
            ],
            "details": [{"rows": [{"label": "Plan", "value": "Business"}]}],
            "providerCost": {
                "used": 12.5,
                "limit": 100,
                "currencyCode": "USD",
                "period": "Monthly",
            },
        },
        "credits": {"remaining": 0, "balanceReadSucceeded": True},
        "api_key": "never-export",
        "error_secret": "never-export",
        **extra,
    }


def test_normalizer_preserves_unknown_zero_and_any_provider(tmp_path):
    raw = [
        export(),
        export("cursor"),
        export("future-provider"),
        export("claude", error={"message": "never-export"}, usage=None, credits=None),
    ]
    normalized = normalize(raw)
    assert len(AccountBatch(snapshots=normalized).snapshots) == 4
    assert "never-export" not in str(normalized)
    assert len(normalized[0]["windows"]) == 2
    assert normalized[0]["windows"][1]["used_percent"] is None
    assert normalized[0]["credits_remaining"] == 0
    assert normalized[0]["spend"]["used"] == 12.5
    assert normalized[-1]["status"] == "error" and normalized[-1]["credits_remaining"] is None
    assert (
        normalize([export(credits={"remaining": 0, "balanceReadSucceeded": False})])[0][
            "credits_remaining"
        ]
        is None
    )
    path = tmp_path / "usage.json"
    path.write_text(json.dumps(raw))
    assert len(collect("not-executed", None, 1, 100000, path)[0]) == 4
    with pytest.raises(ValueError):
        collect("not-executed", None, 1, 1, path)
    for invalid in [
        export(rateWindowLabels=[]),
        export(account="x" * 201),
        export(usage={"identity": []}),
        export(usage={"details": {}}),
    ]:
        with pytest.raises(ValueError):
            normalize([invalid])


def test_accounts_scoped_idempotent_and_not_added_to_usage(system):
    client = system["client"]
    key = client.post(
        "/api/keys",
        json={
            "name": "Laptop",
            "app": "tal-laptop",
            "environment": "desktop",
            "source_type": "codexbar",
        },
    ).json()
    headers = {"Authorization": "Bearer " + key["secret"]}
    body = {"snapshots": normalize([export(), export("cursor")])}
    assert client.post("/api/accounts/snapshots", json=body, headers=headers).json()["updated"] == 2
    assert client.post("/api/accounts/snapshots", json=body, headers=headers).json()["ignored"] == 2
    assert client.get("/api/overview").json()["counts"]["attempts"] == 0
    rows = client.get("/api/accounts").json()
    assert len(rows) == 2 and not rows[0]["stale"]
    assert len(client.get("/api/accounts?provider=cursor").json()) == 1
    assert client.get("/api/accounts?app_name=another").json() == []
    assert client.get("/api/accounts?source=litellm").json() == []
    assert client.get("/api/accounts?environment=production").json() == []
    assert client.get("/api/accounts?model=unrelated").json() == []
    assert client.get("/api/usage/filter-options").json()["provider"] == ["copilot", "cursor"]
    older = {
        **body["snapshots"][0],
        "collected_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
    }
    assert (
        client.post("/api/accounts/snapshots", json={"snapshots": [older]}, headers=headers).json()[
            "ignored"
        ]
        == 1
    )
    invalid = {**older, "collected_at": "2099-01-01T00:00:00Z"}
    assert (
        client.post(
            "/api/accounts/snapshots", json={"snapshots": [invalid]}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/accounts/snapshots",
            json=body,
            headers={"Authorization": "Bearer " + system["key"]["secret"]},
        ).status_code
        == 403
    )
    foreign = system["auth"].issue_key(
        system["other"], "Other", "tal-laptop", "desktop", "codexbar"
    )
    service = system["auth"].service(foreign["secret"])
    Accounts(system["db"]).ingest(service, AccountBatch(snapshots=normalize([export("gemini")])))
    assert len(client.get("/api/accounts").json()) == 2
    session, user, _ = invite_user(system, "viewer")
    membership = MembershipService(system["auth"])
    membership.update(system["owner"], user["user_id"], "viewer", ["different-app"])
    viewer = system["auth"].human(session, system["owner"].tenant_id)
    from dispatcher.reporting import UsageFilter

    assert Accounts(system["db"]).list(viewer, UsageFilter()) == []
    assert client.delete("/api/keys/" + key["id"]).status_code == 204
    assert client.post("/api/accounts/snapshots", json=body, headers=headers).status_code == 401


def test_bridge_cli_contract_partial_results_and_http_sync(system, monkeypatch, tmp_path):
    def run(command, stdout, **kwargs):
        assert command == [
            "codexbar",
            "usage",
            "--format",
            "json",
            "--provider",
            "copilot",
            "--all-accounts",
        ]
        stdout.write(json.dumps([export()]).encode())
        from subprocess import CompletedProcess

        return CompletedProcess(command, 1)

    monkeypatch.setattr(codexbar.subprocess, "run", run)
    snapshots, partial = collect("codexbar", "copilot", 1, 100000, all_accounts=True)
    assert partial and snapshots[0]["provider"] == "copilot"
    key = system["auth"].issue_key(system["owner"], "Local sync", "laptop", "test", "codexbar")
    path = tmp_path / "export.json"
    path.write_text(json.dumps([export()]))
    monkeypatch.setenv("DISPATCHER_URL", "http://testserver")
    monkeypatch.setenv("DISPATCHER_ACCOUNT_KEY", key["secret"])
    monkeypatch.setattr("sys.argv", ["codexbar", "--file", str(path)])
    from contextlib import nullcontext

    monkeypatch.setattr(codexbar.httpx, "Client", lambda **kwargs: nullcontext(system["client"]))
    codexbar.main()
    assert len(system["client"].get("/api/accounts").json()) == 1
    assert system["client"].get("/api/overview").json()["counts"]["attempts"] == 0


def test_account_snapshot_expiry_and_tenant_erasure(system):
    client, db, owner = system["client"], system["db"], system["owner"]
    for principal in (owner, system["other"]):
        key = system["auth"].issue_key(principal, "Device", "laptop", "test", "codexbar")
        Accounts(db).ingest(
            system["auth"].service(key["secret"]), AccountBatch(snapshots=normalize([export()]))
        )
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        connection.execute(
            _SQL_AGE_ACCOUNT, (datetime.now(UTC) - timedelta(days=60), owner.tenant_id)
        )
    assert (
        client.put("/api/retention", json={"attribution_days": 30, "revision": 0}).status_code
        == 200
    )
    with db.tenant(owner.tenant_id) as connection:
        assert (
            Retention(db).tick(connection, owner.tenant_id, datetime.now(UTC))[
                "mem_account_snapshots"
            ]
            == 1
        )
    assert client.get("/api/accounts").json() == []
    deleted = delete_tenant(
        os.environ["TEST_DATABASE_URL"], system["other"].tenant_id, system["other"].tenant_id
    )
    assert deleted["deleted_rows"]["mem_account_snapshots"] == 1


def test_explicit_test_labels_are_reversible_and_apply_to_all_reports(system):
    client = system["client"]
    synthetic, real = event(provider="synthetic-check"), event(provider="real-app")
    ingest(system, [synthetic, real])
    endpoint = f"/api/events/{synthetic['event_id']}/label"
    assert (
        client.put(
            endpoint, json={"is_test": True, "reason": "Confirmed verification fixture"}
        ).status_code
        == 200
    )
    overview = client.get("/api/overview").json()
    assert overview["counts"]["attempts"] == 1 and overview["test_records"] == 1
    assert len(client.get("/api/events").json()) == 1
    assert len(client.get("/api/export/events").json()["events"]) == 1
    assert len(client.get("/api/events?include_test=true").json()) == 2
    assert client.get("/api/events/" + synthetic["event_id"]).json()["is_test"]
    assert "synthetic-check" not in client.get("/api/usage/filter-options").json()["provider"]
    session, _, _ = invite_user(system, "member")
    member = system["auth"].human(session, system["owner"].tenant_id)
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        Reporter(system["db"]).label_test(member, uuid4(), True, "Denied")
    assert client.put(endpoint, json={"is_test": False, "reason": "Restore"}).status_code == 200
    assert client.get("/api/overview").json()["counts"]["attempts"] == 2

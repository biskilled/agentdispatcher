"""Source polling, runtime drift and evaluated edits retain tenant and review boundaries."""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from dispatcher.configuration import Configurations
from dispatcher.configuration_connectors import GitConnector
from dispatcher.configuration_document import ConfigSource
from dispatcher.configuration_monitoring import ConfigurationMonitor
from test_configuration import _DOCUMENT, _FIELDS
from test_integration import event, ingest
from test_policies import assigned, evidence, outcome, setup_experiment

_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"


def source_fixture(system, tmp_path, monkeypatch, **options):
    """Configure only this test's authorised source; private document text stays in the file."""
    (tmp_path / "app.yaml").write_text(_DOCUMENT)
    source = ConfigSource(
        tenant_id=system["owner"].tenant_id,
        app="trader",
        environment="test",
        kind="file",
        root=tmp_path,
        path="app.yaml",
        fields={key: field.model_copy(deep=True) for key, field in _FIELDS.items()},
        writable=True,
        **options,
    )
    monkeypatch.setattr(system["db"].settings, "config_sources", {"app": source})
    return source


def test_polling_runtime_drift_replay_and_unavailable_source(system, tmp_path, monkeypatch, caplog):
    source = source_fixture(system, tmp_path, monkeypatch)
    monitor = ConfigurationMonitor(Configurations(system["db"]))
    at = datetime.now(UTC)
    with ThreadPoolExecutor(2) as workers:
        assert sum(workers.map(lambda _: monitor.poll(at), range(2))) == 1
    client = system["client"]
    current = client.get("/api/configurations/status").json()[0]
    assert current["source_state"] == "current" and current["coverage"] == "no_runtime_evidence"
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    body = {
        "event_id": str(uuid4()),
        "instance_id": "scheduler-one",
        "digest": current["digest"],
        "success": True,
        "occurred_at": at.isoformat(),
    }
    path = "/api/configurations/app/runtime"
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers=headers).json()["inserted"]
    assert not client.post(path, json=body, headers=headers).json()["inserted"]
    assert client.post(path, json={**body, "digest": "0" * 64}, headers=headers).status_code == 409
    foreign = system["auth"].issue_key(system["other"], "other", "trader", "test")
    assert (
        client.post(
            path, json=body, headers={"Authorization": "Bearer " + foreign["secret"]}
        ).status_code
        == 404
    )
    assert monitor.status(system["owner"], at)[0]["instances"][0]["state"] == "matching"
    (tmp_path / "app.yaml").write_text(_DOCUMENT.replace("model-a", "model-b"))
    later = at + timedelta(seconds=system["db"].settings.config_poll_seconds)
    assert monitor.poll(later) == 1
    assert monitor.status(system["owner"], later)[0]["instances"][0]["state"] == "drift"
    # An old export cannot supersede the most recent loaded-version heartbeat.
    old = {
        **body,
        "event_id": str(uuid4()),
        "digest": "0" * 64,
        "occurred_at": (at - timedelta(hours=1)).isoformat(),
    }
    assert client.post(path, json=old, headers=headers).status_code == 200
    assert monitor.status(system["owner"], later)[0]["instances"][0]["digest"] == body["digest"]
    assert (
        monitor.status(system["owner"], at + timedelta(hours=1))[0]["instances"][0]["state"]
        == "stale"
    )
    future = {**body, "event_id": str(uuid4()), "occurred_at": (at + timedelta(days=1)).isoformat()}
    assert client.post(path, json=future, headers=headers).status_code == 422
    (tmp_path / "app.yaml").write_text("private-key: [broken")
    later += timedelta(seconds=system["db"].settings.config_poll_seconds)
    assert monitor.poll(later) == 1
    unavailable = monitor.status(system["owner"], later)[0]
    assert unavailable["source_state"] == "unavailable"
    assert unavailable["instances"][0]["state"] == "source_unavailable"
    assert "private-key" not in caplog.text
    # Target/permission changes invalidate prior runtime evidence rather than implying parity.
    source.writable = False
    assert not monitor.status(system["owner"], later)[0]["instances"]


def test_evaluated_yaml_proposal_uses_cost_quality_and_current_compatibility(
    system, tmp_path, monkeypatch
):
    source_fixture(system, tmp_path, monkeypatch)
    client = system["client"]
    digest = client.post("/api/configurations/app/scan").json()["digest"]
    experiment, _ = setup_experiment(
        system, configuration_source="app", configuration_digest=digest
    )
    path = "/api/configurations/app/recommendations"
    assert client.post(path).json()["suggestions"] == []
    routes = assigned(system, experiment)
    wrong_version = event(
        experiment_id=str(experiment.id),
        assignment_id=routes[0]["assignment_id"],
        variant=routes[0]["variant"],
        config_version="0" * 64,
    )
    assert ingest(system, [wrong_version]).status_code == 409
    for route in routes:
        evidence(system, route, config_version=digest)
        assert outcome(system, route).status_code == 202
    recommendations = client.post(path).json()
    suggestion = recommendations["suggestions"][0]
    assert suggestion["after"] == "model-b" and suggestion["before"] == "model-a"
    assert not suggestion["evidence"]["variants"][0]["proven_savings"]
    request = {
        "digest": recommendations["digest"],
        "experiment_id": str(experiment.id),
        "variant": "candidate",
        "path": "llm.model",
    }
    proposed = client.post(path + "/propose", json=request)
    assert proposed.status_code == 201, proposed.text
    assert (tmp_path / "app.yaml").read_text() == _DOCUMENT
    history = client.get("/api/configurations/changes").json()
    assert history[0]["evaluation"]["experiment"]["id"] == str(experiment.id)
    # More unfinished assigned tasks invalidate promotion eligibility, even for a cached suggestion.
    assigned(system, experiment, 1)
    assert client.post(path + "/propose", json=request).status_code == 409
    system["db"].settings.config_sources["app"].fields["llm.model"].models = ["model-a"]
    assert client.post(path).json()["suggestions"] == []


def test_git_publish_failed_activation_and_reviewed_rollback(system, tmp_path, monkeypatch):
    root, remote = tmp_path / "checkout", tmp_path / "remote.git"
    root.mkdir()
    source = source_fixture(system, root, monkeypatch)
    source.kind = "git"
    source.author_name, source.author_email = "Fixture", "fixture@example.test"
    source.publish_remote = "review"
    subprocess.run(["git", "init", str(root)], capture_output=True, check=True)
    subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True, check=True)
    author = {
        "GIT_AUTHOR_NAME": source.author_name,
        "GIT_COMMITTER_NAME": source.author_name,
        "GIT_AUTHOR_EMAIL": source.author_email,
        "GIT_COMMITTER_EMAIL": source.author_email,
    }
    connector = GitConnector(root, "app.yaml", 65536, author, 5, "review")
    connector._git("add", "app.yaml")
    connector._git("-c", "core.hooksPath=/dev/null", "commit", "-m", "Fixture", extra=author)
    connector._git("remote", "add", "review", str(remote))
    base = connector.read()
    client = system["client"]
    scan = client.post("/api/configurations/app/scan").json()
    proposal = client.post(
        "/api/configurations/app/proposals",
        json={
            "digest": scan["digest"],
            "changes": {"llm.model": "model-b"},
        },
    ).json()
    path = "/api/configurations/changes/" + proposal["id"]
    applied = client.post(path + "/apply").json()
    assert applied["state"] == "review_branch"
    # Retry at the connector boundary returns the same branch, preserving the original checkout.
    text = connector._git("show", applied["revision"].split("@")[1] + ":app.yaml") + "\n"
    assert connector.write(base, text).revision == applied["revision"]
    assert client.post(path + "/publish").status_code == 200
    assert connector.read() == base
    branch, commit = applied["revision"].split("@")
    assert commit in connector._git("ls-remote", "review", branch)
    connector._git("merge", "--ff-only", commit)
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    assert (
        client.post(
            path + "/activation",
            json={"digest": applied["digest"], "success": False},
            headers=headers,
        ).status_code
        == 200
    )
    rollback = client.post(path + "/rollback")
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["state"] == "rollback_review_branch"
    assert client.post(path + "/publish").status_code == 200
    revision = client.get("/api/configurations/changes").json()[0]["result_revision"]
    connector._git("merge", "--ff-only", revision.split("@")[1])
    confirmed = client.post(
        path + "/activation",
        json={"digest": rollback.json()["digest"], "success": True},
        headers=headers,
    )
    assert confirmed.json()["state"] == "rollback_activated", confirmed.text
    assert 'model: "model-a"' in connector.read().text

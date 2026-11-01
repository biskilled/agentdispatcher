"""Review and connector fixtures preserve sources and reject stale or unapproved writes."""

import subprocess
from uuid import uuid4

import httpx
import pytest
from dispatcher.configuration_connectors import (
    ApiConnector,
    FileConnector,
    GitConnector,
    RevisionConflict,
)
from dispatcher.configuration_document import ConfigSource, EditableField, YamlDocument

_DOCUMENT = (
    "# App-owned configuration\nllm:\n  model: model-a # keep comment\n"
    '  temperature: 0.2\nprompt: "private prompt"\napi_key: "private key"\n'
)
_FIELDS = {
    "llm.model": EditableField(kind="model", models=["model-a", "model-b"]),
    "llm.temperature": EditableField(kind="number", minimum=0, maximum=1),
}
_SQL_VERSIONS = "SELECT inventory FROM mem_config_versions WHERE tenant_id=%s"


def test_file_review_activation_failure_rollback_and_scope(system, tmp_path):
    source = tmp_path / "app.yaml"
    source.write_text(_DOCUMENT)
    source_id = "fixture-" + uuid4().hex
    spec = ConfigSource(
        tenant_id=system["owner"].tenant_id,
        app="trader",
        environment="test",
        kind="file",
        root=tmp_path,
        path="app.yaml",
        fields=_FIELDS,
        writable=True,
    )
    system["db"].settings.config_sources[source_id] = spec
    client = system["client"]
    base = "/api/configurations/"
    scanned = client.post(base + source_id + "/scan")
    assert scanned.status_code == 200, scanned.text
    assert "private" not in scanned.text
    with system["db"].tenant(spec.tenant_id) as connection:
        rows = connection.execute(_SQL_VERSIONS, (spec.tenant_id,)).fetchall()
        assert "private" not in str(rows)
    proposal = client.post(
        base + source_id + "/proposals",
        json={"digest": scanned.json()["digest"], "changes": {"llm.model": "model-b"}},
    )
    assert proposal.status_code == 201, proposal.text
    change = base + "changes/" + proposal.json()["id"]
    assert source.read_text() == _DOCUMENT
    other = {"X-Tenant-ID": str(system["other"].tenant_id)}
    assert client.post(change + "/apply", headers=other).status_code == 403
    applied = client.post(change + "/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["state"] == "awaiting_activation"
    assert "# keep comment" in source.read_text() and "private prompt" in source.read_text()
    body = {"digest": applied.json()["digest"], "success": False}
    assert client.post(change + "/activation", json=body).status_code == 401
    headers = {"Authorization": "Bearer " + system["key"]["secret"]}
    activated = client.post(change + "/activation", json=body, headers=headers)
    assert activated.json()["state"] == "activation_failed", activated.text
    assert client.post(change + "/rollback").status_code == 200
    assert 'model: "model-a" # keep comment' in source.read_text()
    assert (
        client.post(
            base + source_id + "/proposals",
            json={"digest": scanned.json()["digest"], "changes": {"llm.model": "model-b"}},
        ).status_code
        == 409
    )
    fresh = client.post(base + source_id + "/scan").json()
    assert (
        client.post(
            base + source_id + "/proposals",
            json={"digest": fresh["digest"], "changes": {"api_key": "changed"}},
        ).status_code
        == 422
    )
    spec.writable = False
    assert (
        client.post(
            base + source_id + "/proposals",
            json={"digest": fresh["digest"], "changes": {"llm.model": "model-b"}},
        ).status_code
        == 403
    )


def test_document_restrictions_and_external_edits(tmp_path):
    document = YamlDocument(_DOCUMENT, _FIELDS, 65536)
    updated, diff = document.replace({"llm.model": "model-b"})
    assert diff == [{"path": "llm.model", "before": "model-a", "after": "model-b"}]
    assert updated == _DOCUMENT.replace("model-a", '"model-b"')
    for text in ["llm: &ref {model: model-a}\nx: *ref", "llm:\n model: model-a\n model: model-b"]:
        with pytest.raises(ValueError):
            YamlDocument(text, _FIELDS, 65536)
    with pytest.raises(ValueError):
        document.replace({"llm.model": "unsupported"})
    with pytest.raises(ValueError):
        document.replace({"llm.temperature": float("nan")})
    file = tmp_path / "app.yaml"
    file.write_text(_DOCUMENT)
    connector = FileConnector(tmp_path, "app.yaml", 65536)
    before = connector.read()
    file.write_text(_DOCUMENT + "# external edit\n")
    with pytest.raises(RevisionConflict):
        connector.write(before, updated)
    with pytest.raises(ValueError):
        FileConnector(tmp_path, "../elsewhere", 65536).read()


def test_conditional_api_connector():
    state = {"text": _DOCUMENT, "etag": '"first"'}

    def server(request):
        if request.method == "PUT":
            if request.headers["if-match"] != state["etag"]:
                return httpx.Response(412)
            state.update(text=request.content.decode(), etag='"second"')
        return httpx.Response(200, text=state["text"], headers={"ETag": state["etag"]})

    connector = ApiConnector(
        "https://fixture.example.test/config", "", 1, 65536, httpx.MockTransport(server)
    )
    original = connector.read()
    text, _ = YamlDocument(original.text, _FIELDS, 65536).replace({"llm.model": "model-b"})
    assert connector.write(original, text).text == text
    with pytest.raises(RevisionConflict):
        connector.write(original, text)
    connector.close()


def test_git_review_branch_preserves_checkout_and_index(tmp_path):
    author = {
        "GIT_AUTHOR_NAME": "Synthetic fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.test",
        "GIT_COMMITTER_NAME": "Synthetic fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.test",
    }
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    file = tmp_path / "app.yaml"
    file.write_text(_DOCUMENT)
    connector = GitConnector(tmp_path, "app.yaml", 65536, author, 5)
    connector._git("add", "app.yaml")
    connector._git("-c", "core.hooksPath=/dev/null", "commit", "-m", "Fixture", extra=author)
    initial = connector.read()
    file.write_text(_DOCUMENT + "# unrelated local edit\n")
    text, _ = YamlDocument(initial.text, _FIELDS, 65536).replace({"llm.model": "model-b"})
    reviewed = connector.write(initial, text)
    assert reviewed.revision.startswith("refs/heads/dispatcher-review/")
    assert connector.read() == initial
    assert file.read_text().endswith("# unrelated local edit\n")
    assert connector._git("diff", "--cached") == ""
    commit = reviewed.revision.split("@")[1]
    assert 'model: "model-b" # keep comment' in connector._git("show", commit + ":app.yaml")

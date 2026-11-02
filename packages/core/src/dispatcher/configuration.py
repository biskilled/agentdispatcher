"""Reviewed configuration changes with durable redacted evidence and explicit app activation."""

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from dispatcher.auth import require_admin
from dispatcher.configuration_connectors import ApiConnector, FileConnector, GitConnector
from dispatcher.configuration_document import Snapshot, YamlDocument
from dispatcher.configuration_monitoring import save_head
from dispatcher.experiments import Experiments

_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_SNAPSHOT = """
INSERT INTO mem_config_versions(tenant_id,source_id,digest,revision,inventory,app,environment)
VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,source_id,digest) DO NOTHING
"""
_SQL_LIST = """
SELECT id,source_id,base_digest,target_digest,rollback_digest,diff,state,result_revision,
evaluation,created_at
FROM mng_config_changes WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s
"""
_SQL_PROPOSAL = """
INSERT INTO mng_config_changes(tenant_id,id,source_id,source_contract,base_digest,
base_revision,target_digest,diff,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_ONE = "SELECT * FROM mng_config_changes WHERE tenant_id=%s AND id=%s FOR UPDATE"
_SQL_STATE = """
UPDATE mng_config_changes SET state=%s,result_revision=%s,updated_at=now()
WHERE tenant_id=%s AND id=%s
"""
_SQL_AUDIT = """
INSERT INTO mem_config_actions(tenant_id,change_id,actor_id,action)
VALUES(%s,%s,%s,%s)
"""
_SQL_ROLLBACK_DIGEST = """
UPDATE mng_config_changes SET rollback_digest=%s WHERE tenant_id=%s AND id=%s
"""
_SQL_EVALUATION = """
UPDATE mng_config_changes SET evaluation=%s WHERE tenant_id=%s AND id=%s
"""


class Configurations:
    """Source YAML remains authoritative; PostgreSQL holds only safe parameters and hashes."""

    def __init__(self, db):
        self.db = db

    def _source(self, principal, source_id, write=False):
        require_admin(principal)
        source = self.db.settings.config_sources.get(source_id)
        if not source or source.tenant_id != principal.tenant_id:
            raise HTTPException(404, "Configuration source not found")
        if write and not source.writable:
            raise HTTPException(403, "Source has no installation write grant")
        return source

    @contextmanager
    def _connector(self, source):
        settings = self.db.settings
        if source.kind == "api":
            if not source.endpoint.startswith(("http://", "https://")):
                raise ValueError("Configuration API endpoint is not configured")
            connector = ApiConnector(
                source.endpoint,
                os.environ[source.token_env] if source.token_env else "",
                settings.http_timeout,
                settings.config_max_bytes,
            )
        elif source.kind == "git":
            if not source.root or not source.author_name or not source.author_email:
                raise ValueError("Git source requires an authorised repository and commit identity")
            author = {
                "GIT_AUTHOR_NAME": source.author_name,
                "GIT_AUTHOR_EMAIL": source.author_email,
                "GIT_COMMITTER_NAME": source.author_name,
                "GIT_COMMITTER_EMAIL": source.author_email,
            }
            connector = GitConnector(
                source.root,
                source.path,
                settings.config_max_bytes,
                author,
                settings.http_timeout,
                source.publish_remote,
            )
        else:
            if not source.root:
                raise ValueError("File source requires an authorised directory")
            connector = FileConnector(source.root, source.path, settings.config_max_bytes)
        try:
            yield connector
        finally:
            if isinstance(connector, ApiConnector):
                connector.close()

    def _document(self, snapshot, source):
        return YamlDocument(snapshot.text, source.fields, self.db.settings.config_max_bytes)

    def sources(self, principal):
        """List authorised source identities without disclosing filesystem paths or credentials."""
        require_admin(principal)
        return [
            {
                "id": key,
                "app": source.app,
                "environment": source.environment,
                "kind": source.kind,
                "writable": source.writable,
                "publishable": bool(source.kind == "git" and source.publish_remote),
                "fields": {name: value.model_dump() for name, value in source.fields.items()},
            }
            for key, source in self.db.settings.config_sources.items()
            if source.tenant_id == principal.tenant_id
        ]

    def scan(self, principal, source_id):
        """Persist safe parameters and hashes; original YAML never enters the database."""
        source = self._source(principal, source_id)
        with self.db.tenant(principal.tenant_id) as connection:
            connection.execute(_SQL_LOCK, (f"{principal.tenant_id}:config-poll:{source_id}",))
            return self.scan_source(connection, source_id, source, datetime.now(UTC))

    def scan_source(self, connection, source_id, source, at):
        """Share redacted discovery between an authorised human scan and the worker."""
        with self._connector(source) as connector:
            snapshot = connector.read()
        inventory = self._document(snapshot, source).inventory()
        connection.execute(
            _SQL_SNAPSHOT,
            (
                source.tenant_id,
                source_id,
                snapshot.digest,
                snapshot.revision,
                Jsonb(inventory),
                source.app,
                source.environment,
            ),
        )
        save_head(connection, source_id, source, snapshot, at)
        return {"digest": snapshot.digest, "revision": snapshot.revision, "inventory": inventory}

    def propose(self, principal, source_id, digest, changes, evaluation=None):
        """Prepare an exact diff against the version the administrator reviewed."""
        source = self._source(principal, source_id, write=True)
        with self._connector(source) as connector:
            snapshot = connector.read()
        if snapshot.digest != digest:
            raise HTTPException(409, "Configuration changed; scan and review it again")
        text, diff = self._document(snapshot, source).replace(changes)
        change_id = uuid4()
        with self.db.tenant(principal.tenant_id) as connection:
            connection.execute(
                _SQL_PROPOSAL,
                (
                    principal.tenant_id,
                    change_id,
                    source_id,
                    source.fingerprint(),
                    digest,
                    snapshot.revision,
                    Snapshot(text, "").digest,
                    Jsonb(diff),
                    principal.subject_id,
                ),
            )
            if evaluation is not None:
                connection.execute(
                    _SQL_EVALUATION,
                    (
                        Jsonb(jsonable_encoder(evaluation, custom_encoder={Decimal: str})),
                        principal.tenant_id,
                        change_id,
                    ),
                )
        return {"id": change_id, "diff": diff, "state": "proposed"}

    def changes(self, principal):
        """Read bounded review history with safe scalar diffs and activation state."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_LIST, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()

    def _load(self, connection, principal, change_id):
        row = connection.execute(_SQL_ONE, (principal.tenant_id, change_id)).fetchone()
        if not row:
            raise HTTPException(404, "Configuration change not found")
        source = self._source(principal, row["source_id"], write=True)
        if source.fingerprint() != row["source_contract"]:
            raise HTTPException(409, "Source permissions or target changed; prepare a new review")
        return row, source

    def apply(self, principal, change_id):
        """Record intent before external I/O; retry reconciles a file/API write after a crash."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            row, source = self._load(connection, principal, change_id)
            if row["state"] not in ("proposed", "applying"):
                raise HTTPException(409, "Change has already left the review stage")
            connection.execute(_SQL_STATE, ("applying", None, principal.tenant_id, change_id))
        with self.db.tenant(principal.tenant_id) as connection:
            row, source = self._load(connection, principal, change_id)
            connection.execute(_SQL_LOCK, (str(principal.tenant_id) + row["source_id"],))
            if row["state"] != "applying":
                raise HTTPException(409, "Another reviewer already applied this change")
            with self._connector(source) as connector:
                current = connector.read()
                if current.digest == row["target_digest"] and source.kind != "git":
                    result = current
                else:
                    if (
                        current.digest != row["base_digest"]
                        or current.revision != row["base_revision"]
                    ):
                        raise HTTPException(
                            409, "Source changed; the reviewed diff cannot be applied"
                        )
                    changes = {item["path"]: item["after"] for item in row["diff"]}
                    text, _ = self._document(current, source).replace(changes)
                    if Snapshot(text, "").digest != row["target_digest"]:
                        raise HTTPException(409, "Reviewed output no longer matches")
                    result = connector.write(current, text)
            state = "review_branch" if source.kind == "git" else "awaiting_activation"
            connection.execute(_SQL_STATE, (state, result.revision, principal.tenant_id, change_id))
            connection.execute(
                _SQL_AUDIT, (principal.tenant_id, change_id, principal.subject_id, "applied")
            )
        return {"state": state, "revision": result.revision, "digest": result.digest}

    def activate(self, principal, change_id, digest, success):
        """Accept reload evidence only from an app-scoped SDK credential."""
        if principal.role != "service" or principal.purpose != "ingest":
            raise HTTPException(403, "App SDK credentials are required for activation evidence")
        with self.db.tenant(principal.tenant_id) as connection:
            row = connection.execute(_SQL_ONE, (principal.tenant_id, change_id)).fetchone()
            source = self.db.settings.config_sources.get(row["source_id"]) if row else None
            if not source or (source.tenant_id, source.app, source.environment) != (
                principal.tenant_id,
                principal.app,
                principal.environment,
            ):
                raise HTTPException(404, "Configuration change not found")
            rollback = row["state"] in {
                "rolled_back",
                "rollback_review_branch",
                "rollback_activated",
                "rollback_activation_failed",
            }
            expected = row["rollback_digest"] if rollback else row["target_digest"]
            state = ("rollback_" if rollback else "") + (
                "activated" if success else "activation_failed"
            )
            if row["state"] == state and digest == expected:
                return {"state": state}
            if (
                row["state"]
                not in (
                    "awaiting_activation",
                    "review_branch",
                    "rolled_back",
                    "rollback_review_branch",
                )
                or digest != expected
            ):
                raise HTTPException(
                    409, "Activation does not match a pending configuration version"
                )
            connection.execute(
                _SQL_STATE, (state, row["result_revision"], principal.tenant_id, change_id)
            )
            connection.execute(
                _SQL_AUDIT, (principal.tenant_id, change_id, principal.subject_id, state)
            )
        return {"state": state}

    def rollback(self, principal, change_id):
        """Restore prior values only if no external edit followed the applied version."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            row, source = self._load(connection, principal, change_id)
            connection.execute(_SQL_LOCK, (str(principal.tenant_id) + row["source_id"],))
            if row["state"] not in ("awaiting_activation", "activated", "activation_failed"):
                raise HTTPException(409, "Change is not eligible for local/API rollback")
            with self._connector(source) as connector:
                current = connector.read()
                if current.digest != row["target_digest"]:
                    raise HTTPException(
                        409, "External edits prevent rollback; prepare a new review"
                    )
                text, _ = self._document(current, source).replace(
                    {item["path"]: item["before"] for item in row["diff"]}
                )
                result = connector.write(current, text)
            state = "rollback_review_branch" if source.kind == "git" else "rolled_back"
            connection.execute(_SQL_STATE, (state, result.revision, principal.tenant_id, change_id))
            connection.execute(
                _SQL_ROLLBACK_DIGEST, (result.digest, principal.tenant_id, change_id)
            )
            connection.execute(
                _SQL_AUDIT, (principal.tenant_id, change_id, principal.subject_id, "rolled_back")
            )
        return {
            "state": state,
            "digest": result.digest,
            "activation": "Application must reload and report the rollback version",
        }

    def publish(self, principal, change_id):
        """Publish an approved Git review branch; merging and deployment remain explicit."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            row, source = self._load(connection, principal, change_id)
            if source.kind != "git" or row["state"] not in {
                "review_branch",
                "rollback_review_branch",
            }:
                raise HTTPException(409, "No pending Git review branch to publish")
            with self._connector(source) as connector:
                revision = connector.publish(row["result_revision"])
            connection.execute(
                _SQL_AUDIT,
                (principal.tenant_id, change_id, principal.subject_id, "branch.published"),
            )
        return {"revision": revision, "state": row["state"]}

    def recommendations(self, principal, source_id):
        """Suggest only compatible candidates that pass the existing full-task evaluation gates."""
        source = self._source(principal, source_id)
        current = self.scan(principal, source_id)
        experiments = Experiments(self.db)
        suggestions = []
        for row in experiments.list(principal):
            config = row["config"]
            if (config["app"], config["environment"]) != (source.app, source.environment):
                continue
            if (config.get("configuration_source"), config.get("configuration_digest")) != (
                source_id,
                current["digest"],
            ):
                continue
            result = experiments.results(principal, row["id"])
            baseline = next(
                item["model"]
                for item in result["variants"]
                if item["variant"] == config["baseline"]
            )
            for candidate in result["variants"]:
                if not candidate["eligible"]:
                    continue
                for path, field in source.fields.items():
                    if (
                        field.kind == "model"
                        and current["inventory"][path] == baseline
                        and candidate["model"] in field.models
                    ):
                        suggestions.append(
                            {
                                "experiment_id": row["id"],
                                "variant": candidate["variant"],
                                "path": path,
                                "before": baseline,
                                "after": candidate["model"],
                                "evidence": result,
                            }
                        )
        return {"digest": current["digest"], "suggestions": suggestions}

    def propose_recommendation(self, principal, source_id, digest, experiment_id, variant, path):
        """Recheck current evaluation gates and preserve the evidence with the reviewed diff."""
        recommendations = self.recommendations(principal, source_id)
        if recommendations["digest"] != digest:
            raise HTTPException(409, "Configuration changed; review recommendations again")
        selected = next(
            (
                item
                for item in recommendations["suggestions"]
                if str(item["experiment_id"]) == str(experiment_id)
                and item["variant"] == variant
                and item["path"] == path
            ),
            None,
        )
        if not selected:
            raise HTTPException(409, "Candidate no longer meets evaluation and compatibility gates")
        return self.propose(
            principal, source_id, digest, {path: selected["after"]}, evaluation=selected["evidence"]
        )

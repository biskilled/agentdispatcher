"""One routing policy engine serves HTTP controls, LiteLLM callbacks and authorized tools."""

import hashlib
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from dispatcher.auth import require_admin
from dispatcher.policy_contracts import Experiment, ModelPolicy

_SQL_LIST = "SELECT * FROM mng_model_policies WHERE tenant_id=%s ORDER BY id"
_SQL_CURRENT = "SELECT * FROM mng_model_policies WHERE tenant_id=%s AND id=%s"
_SQL_ACTIVE = "SELECT * FROM mng_model_policies WHERE tenant_id=%s AND app=%s AND environment=%s"
_SQL_HISTORY = """
SELECT revision,config,actor_id,action,evidence,created_at FROM mem_policy_versions
WHERE tenant_id=%s AND policy_id=%s ORDER BY revision DESC
"""
_SQL_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))"
_SQL_PUT = """
INSERT INTO mng_model_policies(tenant_id,id,app,environment,revision,config)
VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,id) DO UPDATE
SET revision=EXCLUDED.revision,config=EXCLUDED.config,updated_at=now()
"""
_SQL_VERSION = """
INSERT INTO mem_policy_versions(tenant_id,policy_id,revision,config,actor_id,action,evidence)
VALUES(%s,%s,%s,%s,%s,%s,%s)
"""
_SQL_EXPERIMENT = "SELECT * FROM mng_experiments WHERE tenant_id=%s AND id=%s"
_SQL_ASSIGNMENT = """
SELECT * FROM mem_assignments WHERE tenant_id=%s AND experiment_id=%s AND task_id=%s
"""
_SQL_ASSIGN = """
INSERT INTO mem_assignments(tenant_id,id,experiment_id,task_id,variant,model)
VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING
"""


def pick_variant(experiment, tenant_id, task_id):
    """Stable hashing keeps all retries and steps for an assigned task in the same variant."""
    value = f"{experiment.seed}:{tenant_id}:{experiment.id}:{task_id}"
    bucket = int.from_bytes(hashlib.sha256(value.encode()).digest(), "big")
    bucket %= sum(variant.weight for variant in experiment.variants)
    for variant in experiment.variants:
        if bucket < variant.weight:
            return variant
        bucket -= variant.weight
    raise AssertionError("Validated variants must exhaust the assignment bucket")


class Policies:
    """Apply optimistic changes, retain revisions, and enforce model capability declarations."""

    def __init__(self, db):
        self.db = db

    def list(self, principal):
        """List policies only for administrators of the authenticated tenant."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(_SQL_LIST, (principal.tenant_id,)).fetchall()

    def history(self, principal, policy_id):
        """Return immutable policy configurations with actor/action evidence."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(_SQL_HISTORY, (principal.tenant_id, policy_id)).fetchall()

    def put(self, principal, config, revision, action="updated"):
        """Change effective routing immediately; optimistic revision prevents lost updates."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return self._put(connection, principal, config, revision, action)

    def _put(self, connection, principal, config, revision, action, evidence=None):
        connection.execute(_SQL_LOCK, (f"{principal.tenant_id}:policies",))
        current = connection.execute(_SQL_CURRENT, (principal.tenant_id, config.id)).fetchone()
        if (current["revision"] if current else 0) != revision:
            raise HTTPException(409, "Policy revision changed; reload before saving")
        if current and (current["app"], current["environment"]) != (config.app, config.environment):
            raise HTTPException(409, "An existing policy cannot change application scope")
        active = connection.execute(
            _SQL_ACTIVE, (principal.tenant_id, config.app, config.environment)
        ).fetchone()
        if active and active["id"] != config.id:
            raise HTTPException(409, "This application scope already has a policy")
        if config.experiment_id:
            experiment = self._experiment(connection, principal, config.experiment_id)
            if (experiment.app, experiment.environment) != (config.app, config.environment):
                raise HTTPException(403, "Experiment scope does not match policy")
            if {variant.model for variant in experiment.variants} - set(config.allowed_models):
                raise HTTPException(400, "Every experiment candidate must satisfy the model policy")
        next_revision = revision + 1
        payload = Jsonb(config.model_dump(mode="json"))
        connection.execute(
            _SQL_PUT,
            (
                principal.tenant_id,
                config.id,
                config.app,
                config.environment,
                next_revision,
                payload,
            ),
        )
        connection.execute(
            _SQL_VERSION,
            (
                principal.tenant_id,
                config.id,
                next_revision,
                payload,
                principal.subject_id,
                action,
                Jsonb(evidence),
            ),
        )
        return {"id": config.id, "revision": next_revision}

    def rollback(self, principal, policy_id, revision, target_revision):
        """Restore a selected immutable configuration as a new audited effective revision."""
        history = self.history(principal, policy_id)
        target = next((row for row in history if row["revision"] == target_revision), None)
        if not target:
            raise HTTPException(404, "Policy version not found")
        return self.put(
            principal,
            ModelPolicy.model_validate(target["config"]),
            revision,
            action=f"rollback:{target_revision}",
        )

    def _experiment(self, connection, principal, experiment_id):
        row = connection.execute(_SQL_EXPERIMENT, (principal.tenant_id, experiment_id)).fetchone()
        if not row:
            raise HTTPException(404, "Experiment not found")
        return Experiment.model_validate(row["config"])

    def route(self, principal, requested_model, task_id):
        """Select an effective route without allowing a caller to bypass its app's policy."""
        with self.db.tenant(principal.tenant_id) as connection:
            row = connection.execute(
                _SQL_ACTIVE, (principal.tenant_id, principal.app, principal.environment)
            ).fetchone()
            result = {
                "requested_model": requested_model,
                "model": requested_model,
                "fallbacks": [],
                "policy_version": None,
            }
            if not row:
                return result
            config = ModelPolicy.model_validate(row["config"])
            if requested_model not in config.allowed_models:
                raise HTTPException(403, "Requested model is not allowed by the active policy")
            result.update(
                model=config.primary or requested_model,
                fallbacks=config.fallbacks,
                policy_version=f"{config.id}:{row['revision']}",
            )
            if config.experiment_id:
                experiment = self._experiment(connection, principal, config.experiment_id)
                variant = pick_variant(experiment, principal.tenant_id, task_id)
                connection.execute(
                    _SQL_ASSIGN,
                    (
                        principal.tenant_id,
                        uuid4(),
                        experiment.id,
                        task_id,
                        variant.name,
                        variant.model,
                    ),
                )
                assignment = connection.execute(
                    _SQL_ASSIGNMENT, (principal.tenant_id, experiment.id, task_id)
                ).fetchone()
                result.update(
                    model=assignment["model"],
                    experiment_id=str(experiment.id),
                    assignment_id=str(assignment["id"]),
                    variant=assignment["variant"],
                )
            result["fallbacks"] = [
                model for model in result["fallbacks"] if model != result["model"]
            ]
            return result

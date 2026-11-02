"""Task-level evaluation includes retries, failures, evaluation calls and declared allocations."""

from decimal import Decimal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb

from dispatcher.auth import require_admin, validate_scope
from dispatcher.policies import Policies
from dispatcher.policy_contracts import Experiment, ModelPolicy

_SQL_ADD = """
INSERT INTO mng_experiments(tenant_id,id,app,environment,config,created_by)
VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id
"""
_SQL_ONE = "SELECT config FROM mng_experiments WHERE tenant_id=%s AND id=%s"
_SQL_LIST = """
SELECT id,config,created_at FROM mng_experiments WHERE tenant_id=%s
ORDER BY created_at DESC LIMIT %s
"""
_SQL_ASSIGNMENT = """
SELECT a.*,e.app,e.environment FROM mem_assignments a JOIN mng_experiments e
ON (e.tenant_id,e.id)=(a.tenant_id,a.experiment_id) WHERE a.tenant_id=%s AND a.id=%s
"""
_SQL_FEEDBACK = """
INSERT INTO mem_task_outcomes(tenant_id,assignment_id,outcome) VALUES(%s,%s,%s)
ON CONFLICT DO NOTHING RETURNING assignment_id
"""
_SQL_FEEDBACK_ONE = "SELECT outcome FROM mem_task_outcomes WHERE tenant_id=%s AND assignment_id=%s"
_SQL_RESULTS = """
WITH tasks AS (
 SELECT a.id,a.variant,o.outcome,count(u.event_id) attempts,
 count(u.event_id) FILTER(WHERE u.cost IS NULL OR u.currency<>%s) unknown_costs,
 coalesce(sum(u.cost) FILTER(WHERE u.currency=%s),0) observed_cost,
 coalesce(sum(u.cost) FILTER(WHERE u.currency=%s AND u.payload->>'usage_category'='evaluation'),0)
 evaluation_cost FROM mem_assignments a LEFT JOIN mem_task_outcomes o
 ON (o.tenant_id,o.assignment_id)=(a.tenant_id,a.id) LEFT JOIN mem_usage u
 ON u.tenant_id=a.tenant_id AND u.payload->>'assignment_id'=a.id::text
 WHERE a.tenant_id=%s AND a.experiment_id=%s GROUP BY a.id,a.variant,o.outcome
)
SELECT variant,count(*) assigned,sum(attempts)::bigint attempts,
 count(*) FILTER(WHERE outcome->>'status'='completed') completed,
 count(*) FILTER(WHERE outcome IS NULL) missing_feedback,
 count(*) FILTER(WHERE attempts=0) unobserved_tasks,
 sum(unknown_costs)::bigint unknown_costs,
 count(*) FILTER(WHERE outcome IS NOT NULL AND
   (NOT (outcome->>'coverage_complete')::boolean OR NOT (outcome->>'fees_accounted')::boolean
    OR outcome->>'currency'<>%s)) incomplete_costs,
 avg((outcome->>'quality')::numeric) quality,
 avg((outcome->>'duration_ms')::numeric) latency_ms,
 sum(observed_cost+CASE WHEN outcome->>'currency'=%s
 THEN coalesce((outcome->>'additional_cost')::numeric,0) ELSE 0 END) task_cost,
 sum(evaluation_cost) evaluation_cost
FROM tasks GROUP BY variant
"""
_SQL_ACTIVE = "SELECT * FROM mng_model_policies WHERE tenant_id=%s AND id=%s"


def validate_assignment(connection, principal, event):
    """An experiment label must refer to an assigned task within this service's app scope."""
    if not event.assignment_id:
        return
    row = connection.execute(_SQL_ASSIGNMENT, (principal.tenant_id, event.assignment_id)).fetchone()
    if not row or (row["app"], row["environment"]) != (principal.app, principal.environment):
        raise HTTPException(403, "Experiment assignment is outside the service scope")
    if (row["experiment_id"], row["variant"]) != (event.experiment_id, event.variant):
        raise HTTPException(409, "Experiment evidence does not match its assignment")


class Experiments:
    """Evaluate against declared gates; app-attested coverage is never called proven savings."""

    def __init__(self, db):
        self.db = db
        self.policies = Policies(db)

    def create(self, principal, config):
        """Store immutable candidate/seed/gate settings before any assignment is made."""
        require_admin(principal)
        payload = config.model_dump(mode="json")
        with self.db.tenant(principal.tenant_id) as connection:
            row = connection.execute(
                _SQL_ADD,
                (
                    principal.tenant_id,
                    config.id,
                    config.app,
                    config.environment,
                    Jsonb(payload),
                    principal.subject_id,
                ),
            ).fetchone()
            if not row:
                existing = connection.execute(_SQL_ONE, (principal.tenant_id, config.id)).fetchone()
                if not existing or existing["config"] != payload:
                    raise HTTPException(409, "Experiment already exists with different settings")
        return {"id": config.id}

    def list(self, principal):
        """Return only this tenant's experiments, with a bounded response size."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_LIST, (principal.tenant_id, self.db.settings.page_size)
            ).fetchall()

    def feedback(self, principal, outcome):
        """Append a final task outcome once; changed feedback requires a new experiment."""
        validate_scope(principal, outcome)
        payload = outcome.model_dump(mode="json")
        with self.db.tenant(principal.tenant_id) as connection:
            assignment = connection.execute(
                _SQL_ASSIGNMENT, (principal.tenant_id, outcome.assignment_id)
            ).fetchone()
            if not assignment or (assignment["app"], assignment["environment"]) != (
                principal.app,
                principal.environment,
            ):
                raise HTTPException(403, "Experiment assignment is outside the service scope")
            added = connection.execute(
                _SQL_FEEDBACK, (principal.tenant_id, outcome.assignment_id, Jsonb(payload))
            ).fetchone()
            if not added:
                existing = connection.execute(
                    _SQL_FEEDBACK_ONE, (principal.tenant_id, outcome.assignment_id)
                ).fetchone()
                if not existing or existing["outcome"] != payload:
                    raise HTTPException(409, "Task outcome conflicts with accepted evidence")
        return {"inserted": bool(added)}

    def results(self, principal, experiment_id):
        """Include all assigned-task spend, dividing by successful tasks rather than attempts."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return self._results(connection, principal, experiment_id)

    def _results(self, connection, principal, experiment_id):
        row = connection.execute(_SQL_ONE, (principal.tenant_id, experiment_id)).fetchone()
        if not row:
            raise HTTPException(404, "Experiment not found")
        config = Experiment.model_validate(row["config"])
        rows = connection.execute(
            _SQL_RESULTS,
            (
                config.currency,
                config.currency,
                config.currency,
                principal.tenant_id,
                experiment_id,
                config.currency,
                config.currency,
            ),
        ).fetchall()
        results = {row["variant"]: self._summarize(row, config) for row in rows}
        baseline = results.get(config.baseline)
        for variant in config.variants:
            candidate = results.setdefault(
                variant.name,
                {"variant": variant.name, "assigned": 0, "reasons": ["No assignments"]},
            )
            candidate.update(model=variant.model, eligible=False, proven_savings=False)
            if variant.name == config.baseline:
                continue
            if not baseline or baseline["reasons"]:
                candidate["reasons"].append("Baseline has insufficient evidence")
                continue
            if candidate["reasons"]:
                continue
            if candidate["quality"] < baseline["quality"] - config.quality_margin:
                candidate["reasons"].append("Quality is below the configured baseline tolerance")
            if candidate["success_rate"] < baseline["success_rate"]:
                candidate["reasons"].append("Task success rate is below the baseline")
            if candidate["cost_per_success"] >= baseline["cost_per_success"]:
                candidate["reasons"].append("No lower full-task cost observed")
            candidate["eligible"] = not candidate["reasons"]
            if candidate["eligible"]:
                candidate["observed_savings_per_success"] = (
                    baseline["cost_per_success"] - candidate["cost_per_success"]
                )
        return {
            "experiment": config.model_dump(mode="json"),
            "variants": list(results.values()),
            "evidence": (
                "App-provided quality and coverage; configured promotion gates, "
                "not a statistical proof"
            ),
        }

    def _summarize(self, row, config):
        row["reasons"] = []
        row["success_rate"] = Decimal(row["completed"]) / row["assigned"]
        row["cost_per_success"] = row["task_cost"] / row["completed"] if row["completed"] else None
        checks = (
            (row["assigned"] < config.minimum_tasks, "Minimum assigned task count not reached"),
            (not row["completed"], "No successful tasks"),
            (row["missing_feedback"] > 0, "Missing final quality/cost feedback"),
            (row["unobserved_tasks"] > 0, "Assigned tasks have no usage evidence"),
            (row["unknown_costs"] > 0, "Unknown cost or mixed currencies"),
            (row["incomplete_costs"] > 0, "Coverage or fee allocation is incomplete"),
            (
                row["quality"] is None or row["quality"] < config.minimum_quality,
                "Quality gate not met",
            ),
            (
                row["latency_ms"] is None or row["latency_ms"] > config.maximum_latency_ms,
                "Latency gate not met",
            ),
        )
        row["reasons"].extend(message for failed, message in checks if failed)
        return row

    def promote(self, principal, experiment_id, variant, policy_id, revision):
        """Recheck evaluation and compatibility, then activate an audited routing revision."""
        require_admin(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            current = connection.execute(_SQL_ACTIVE, (principal.tenant_id, policy_id)).fetchone()
            if not current or current["revision"] != revision:
                raise HTTPException(409, "Policy revision changed; reload before promoting")
            policy = ModelPolicy.model_validate(current["config"])
            if policy.experiment_id != experiment_id:
                raise HTTPException(409, "The policy is not running this experiment")
            results = self._results(connection, principal, experiment_id)
            selected = next((row for row in results["variants"] if row["variant"] == variant), None)
            if not selected or not selected["eligible"]:
                raise HTTPException(409, "Candidate does not meet the configured evaluation gates")
            config = ModelPolicy.model_validate(
                {**policy.model_dump(), "primary": selected["model"], "experiment_id": None}
            )
            return self.policies._put(
                connection,
                principal,
                config,
                revision,
                action=f"promote:{experiment_id}:{variant}",
                evidence=jsonable_encoder(results, custom_encoder={Decimal: str}),
            )

"""Policy and experiment controls bind browser roles and ingestion service scopes separately."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field

from dispatcher.contracts import Contract
from dispatcher.policy_contracts import Experiment, ModelPolicy, TaskOutcome


class PolicyRequest(Contract):
    """An optimistic policy update cannot silently overwrite another administrator's edit."""

    config: ModelPolicy
    revision: int = Field(default=0, ge=0)


class RollbackRequest(Contract):
    """Restore one known revision under a current-revision precondition."""

    revision: int = Field(ge=1)
    target_revision: int = Field(ge=1)


class PromotionRequest(Contract):
    """Promotion is explicit, audited and bound to the evaluated policy revision."""

    variant: str = Field(min_length=1, max_length=100)
    policy_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)


class RouteRequest(Contract):
    """Use one stable job/operation UUID across initial selection and all gateway requests."""

    model: str = Field(min_length=1, max_length=100)
    task_id: UUID


def routes(policies, experiments, human, service, respond):
    """Expose reusable policy/evaluation services through the common permission boundary."""
    router = APIRouter(prefix="/api")

    @router.post("/policies/route")
    def route(body: RouteRequest, principal=Depends(service)):
        """Let an app obtain its task assignment before recording multi-step/evaluation usage."""
        return policies.route(principal, body.model, body.task_id)

    @router.get("/policies")
    def list_policies(principal=Depends(human)):
        """Read active policy revisions."""
        return policies.list(principal)

    @router.put("/policies")
    def put_policy(body: PolicyRequest, principal=Depends(human)):
        """Activate a validated declarative policy immediately for future gateway requests."""
        return policies.put(principal, body.config, body.revision)

    @router.get("/policies/{policy_id}/history")
    def history(policy_id: str, principal=Depends(human)):
        """Read immutable versions and promotion evidence."""
        return policies.history(principal, policy_id)

    @router.post("/policies/{policy_id}/rollback")
    def rollback(policy_id: str, body: RollbackRequest, principal=Depends(human)):
        """Restore prior routing as a new effective revision."""
        return policies.rollback(principal, policy_id, body.revision, body.target_revision)

    @router.get("/experiments")
    def list_experiments(principal=Depends(human)):
        """Read this tenant's experiment configurations."""
        return experiments.list(principal)

    @router.post("/experiments", status_code=201)
    def create_experiment(body: Experiment, principal=Depends(human)):
        """Create immutable candidates and evaluation gates."""
        return experiments.create(principal, body)

    @router.get("/experiments/{experiment_id}")
    def results(experiment_id: UUID, principal=Depends(human)):
        """Compare whole-task cost and quality, retaining uncertainty and failures."""
        return respond(experiments.results(principal, experiment_id))

    @router.post("/experiments/{experiment_id}/promote")
    def promote(experiment_id: UUID, body: PromotionRequest, principal=Depends(human)):
        """Recheck compatibility/evaluation and activate a reversible model selection."""
        return experiments.promote(
            principal, experiment_id, body.variant, body.policy_id, body.revision
        )

    @router.post("/experiments/outcomes", status_code=202)
    def outcome(body: TaskOutcome, principal=Depends(service)):
        """Accept metadata-only quality and coverage feedback from the authorized app."""
        return experiments.feedback(principal, body)

    return router

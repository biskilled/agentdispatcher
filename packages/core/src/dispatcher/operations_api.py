"""HTTP boundaries for schedule observation and budget administration."""

from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import Field

from dispatcher.contracts import Contract
from dispatcher.operations import Budget, Schedule


class ScheduleRequest(Contract):
    """Optimistic schedule registration or update."""

    config: Schedule
    revision: int = Field(default=0, ge=0)


class BudgetRequest(Contract):
    """Optimistic budget configuration update."""

    config: Budget
    revision: int = Field(default=0, ge=0)


def routes(operations, human):
    """Bind all monitoring administration routes to the common human authorization dependency."""
    router = APIRouter(prefix="/api")

    @router.get("/schedules")
    def schedules(principal=Depends(human)):
        """Read external application schedules without executing them."""
        return operations.list(principal, "schedules")

    @router.put("/schedules")
    def schedule(body: ScheduleRequest, principal=Depends(human)):
        """Register a cadence or revise its settings."""
        return operations.put(principal, "schedules", body.config, body.revision)

    @router.get("/schedules/health")
    def health(principal=Depends(human)):
        """Include missed occurrences even when the app never emitted a start event."""
        return operations.health(principal)

    @router.get("/budgets")
    def budgets(principal=Depends(human)):
        """Read budget configuration revisions."""
        return operations.list(principal, "budgets")

    @router.put("/budgets")
    def budget(body: BudgetRequest, principal=Depends(human)):
        """Change monitoring thresholds; this does not deny provider requests."""
        return operations.put(principal, "budgets", body.config, body.revision)

    @router.get("/budgets/usage")
    def spend(principal=Depends(human)):
        """Return exact decimal budget counters with separate fees and uncertainty."""
        return JSONResponse(
            jsonable_encoder(operations.budgets(principal), custom_encoder={Decimal: str})
        )

    return router

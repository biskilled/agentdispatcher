"""Review actions use human permissions; activation evidence requires scoped SDK authentication."""

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from dispatcher.configuration_connectors import RevisionConflict
from dispatcher.contracts import Contract


class Proposal(Contract):
    """The reviewed content hash and explicitly selected scalar updates."""

    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    changes: dict[str, str | int | float | bool] = Field(min_length=1, max_length=100)


class Activation(Contract):
    """Version loaded by the application and its activation outcome."""

    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    success: bool


def _call(method, *args):
    try:
        return method(*args)
    except RevisionConflict:
        raise HTTPException(409, "Source changed; scan and review again") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    except (OSError, httpx.HTTPError):
        raise HTTPException(
            502, "Configured source is unavailable; no activation was confirmed"
        ) from None


def routes(configurations, human, service):
    """Reuse existing authorization dependencies without exposing connector credentials."""
    router = APIRouter(prefix="/api/configurations")

    @router.get("")
    def sources(principal=Depends(human)):
        """List sources authorized by the installation operator."""
        return configurations.sources(principal)

    @router.get("/changes")
    def changes(principal=Depends(human)):
        """Read redacted review and activation history."""
        return configurations.changes(principal)

    @router.post("/{source_id}/scan")
    def scan(source_id: str, principal=Depends(human)):
        """Discover the latest permitted values."""
        return _call(configurations.scan, principal, source_id)

    @router.post("/{source_id}/proposals", status_code=201)
    def propose(source_id: str, body: Proposal, principal=Depends(human)):
        """Prepare a proposal for a separate explicit apply action."""
        return _call(configurations.propose, principal, source_id, body.digest, body.changes)

    @router.post("/changes/{change_id}/apply")
    def apply(change_id: UUID, principal=Depends(human)):
        """Apply a reviewed diff; Git creates a review branch."""
        return _call(configurations.apply, principal, change_id)

    @router.post("/changes/{change_id}/rollback")
    def rollback(change_id: UUID, principal=Depends(human)):
        """Restore prior parameter values without overwriting external edits."""
        return _call(configurations.rollback, principal, change_id)

    @router.post("/changes/{change_id}/activation")
    def activation(change_id: UUID, body: Activation, principal=Depends(service)):
        """Accept activation evidence only from the configured application/environment."""
        return configurations.activate(principal, change_id, body.digest, body.success)

    return router

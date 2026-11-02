"""Review actions use human permissions; activation evidence requires scoped SDK authentication."""

from decimal import Decimal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import Field

from dispatcher.configuration_connectors import RevisionConflict
from dispatcher.configuration_monitoring import ConfigurationMonitor, RuntimeVersion
from dispatcher.contracts import Contract


class Proposal(Contract):
    """The reviewed content hash and explicitly selected scalar updates."""

    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    changes: dict[str, str | int | float | bool] = Field(min_length=1, max_length=100)


class Activation(Contract):
    """Version loaded by the application and its activation outcome."""

    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    success: bool


class Recommendation(Contract):
    """Identify existing evaluation evidence; client-provided scores are never accepted."""

    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_id: UUID
    variant: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=200)


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
    monitor = ConfigurationMonitor(configurations)

    @router.get("/status")
    def status(principal=Depends(human)):
        """Read source freshness and per-instance runtime drift."""
        return monitor.status(principal)

    @router.post("/{source_id}/runtime")
    def runtime(source_id: str, body: RuntimeVersion, principal=Depends(service)):
        """Record an app-scoped loaded-version heartbeat."""
        return monitor.runtime(principal, source_id, body)

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

    @router.post("/{source_id}/recommendations")
    def recommendations(source_id: str, principal=Depends(human)):
        """Read fresh evaluated alternatives without changing the authoritative source."""
        return jsonable_encoder(
            _call(configurations.recommendations, principal, source_id),
            custom_encoder={Decimal: str},
        )

    @router.post("/{source_id}/recommendations/propose", status_code=201)
    def recommend(source_id: str, body: Recommendation, principal=Depends(human)):
        """Prepare a separate reviewed diff after rechecking evidence and source version."""
        return _call(
            configurations.propose_recommendation,
            principal,
            source_id,
            body.digest,
            body.experiment_id,
            body.variant,
            body.path,
        )

    @router.post("/changes/{change_id}/apply")
    def apply(change_id: UUID, principal=Depends(human)):
        """Apply a reviewed diff; Git creates a review branch."""
        return _call(configurations.apply, principal, change_id)

    @router.post("/changes/{change_id}/rollback")
    def rollback(change_id: UUID, principal=Depends(human)):
        """Restore prior parameter values without overwriting external edits."""
        return _call(configurations.rollback, principal, change_id)

    @router.post("/changes/{change_id}/publish")
    def publish(change_id: UUID, principal=Depends(human)):
        """Publish only a prepared review branch to the source's approved remote."""
        return _call(configurations.publish, principal, change_id)

    @router.post("/changes/{change_id}/activation")
    def activation(change_id: UUID, body: Activation, principal=Depends(service)):
        """Accept activation evidence only from the configured application/environment."""
        return configurations.activate(principal, change_id, body.digest, body.success)

    return router

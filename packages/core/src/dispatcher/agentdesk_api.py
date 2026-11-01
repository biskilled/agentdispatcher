"""Account-link controls and fresh-credential AgentDesk reads share Dispatcher permissions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import Field, SecretStr

from dispatcher.contracts import Contract
from dispatcher.reporting import UsageFilter


class Credential(Contract):
    """A transient remote credential; never persisted or returned."""

    token: SecretStr = Field(min_length=1, max_length=16384)


def routes(adapter, reporter, human, respond, session_cookie):
    """Keep browser CSRF/session checks separate from explicit bearer-token tool access."""
    router = APIRouter()

    def recent(request, principal):
        user = adapter.auth.recent_user(request.cookies.get(session_cookie, ""))
        if user["user_id"] != principal.subject_id:
            raise HTTPException(401, "Sign in again before connecting AgentDesk")

    def remote(
        tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
        authorization: Annotated[str, Header()] = "",
    ):
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(401, "AgentDesk bearer token required")
        return adapter.principal(token, tenant_id)

    @router.get("/api/agentdesk/connection")
    def status(principal=Depends(human)):
        """Show this workspace's binding and the caller's personal link status."""
        return adapter.status(principal)

    @router.post("/api/agentdesk/bind", status_code=204)
    def bind(body: Credential, request: Request, principal=Depends(human)):
        """Require recent local login and administration of both tenants."""
        recent(request, principal)
        adapter.bind(principal, body.token.get_secret_value())

    @router.post("/api/agentdesk/link", status_code=204)
    def link(body: Credential, request: Request, principal=Depends(human)):
        """Explicitly link only this signed-in person's existing membership."""
        recent(request, principal)
        adapter.link(principal, body.token.get_secret_value())

    @router.delete("/api/agentdesk/link", status_code=204)
    def unlink(principal=Depends(human)):
        """Remove this person's remote access immediately."""
        adapter.disconnect(principal)

    @router.delete("/api/agentdesk/bind", status_code=204)
    def disconnect(principal=Depends(human)):
        """Let the owner disconnect this workspace and all linked accounts."""
        adapter.disconnect(principal, tenant=True)

    @router.get("/api/agentdesk/usage")
    def usage(filters: Annotated[UsageFilter, Query()], principal=Depends(remote)):
        """Read usage using live AgentDesk identity and current Dispatcher permissions."""
        return respond(reporter.overview(principal, filters))

    @router.get("/api/agentdesk/sessions/{session_id}")
    def session(session_id: str, principal=Depends(remote)):
        """Return a scoped session summary; a guessed session ID grants no visibility."""
        return respond(
            reporter.overview(principal, UsageFilter(session_id=session_id, group_by="work_item"))
        )

    return router

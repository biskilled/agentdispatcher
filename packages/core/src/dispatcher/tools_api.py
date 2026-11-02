"""Authorized tool operations share browser reporting and model-policy services."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from dispatcher.contracts import Contract
from dispatcher.policies_api import PolicyRequest
from dispatcher.reporting import UsageFilter


class ToolGrant(Contract):
    """Policy writes require separate consent and a current administrator role."""

    can_write_policy: bool = False


def routes(access, reporter, policies, experiments, human, respond, session_cookie):
    """Accept dedicated tool credentials; never infer permissions from tool arguments."""
    router = APIRouter(prefix="/api/tools")

    def grant(
        request: Request,
        tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
        authorization: Annotated[str, Header()] = "",
    ):
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.startswith("dta_"):
            raise HTTPException(401, "Delegated tool credential required")
        return access.principal(token, tenant_id, write=request.method not in {"GET", "HEAD"})

    @router.get("/access")
    def tokens(principal=Depends(human)):
        """List personal tool credential metadata."""
        return access.list(principal)

    @router.post("/access", status_code=201)
    def issue(body: ToolGrant, request: Request, principal=Depends(human)):
        """Grant explicit session-bound access from a CSRF-protected browser request."""
        return access.issue(
            request.cookies.get(session_cookie, ""), principal.tenant_id, body.can_write_policy
        )

    @router.delete("/access/{token_id}", status_code=204)
    def revoke(token_id: UUID, principal=Depends(human)):
        """Remove one personal grant."""
        access.revoke(principal, token_id)

    @router.get("/me")
    def me(verified=Depends(grant)):
        """Verify credentials for an MCP resource server without exposing a mailbox."""
        principal, row = verified
        return {
            "tenant_id": principal.tenant_id,
            "user_id": principal.subject_id,
            "expires_at": row["expires_at"],
            "resource": row["resource"],
            "role": principal.role,
            "can_write_policy": row["can_write_policy"] and principal.role in {"owner", "admin"},
        }

    @router.get("/usage")
    def usage(filters: Annotated[UsageFilter, Query()], verified=Depends(grant)):
        """Read usage with the dashboard's role/app/user restrictions."""
        return respond(reporter.overview(verified[0], filters))

    @router.get("/sessions/{session_id}")
    def session(session_id: str, verified=Depends(grant)):
        """Get session totals without granting access from its identifier."""
        return respond(
            reporter.overview(verified[0], UsageFilter(session_id=session_id, group_by="work_item"))
        )

    @router.get("/experiments")
    def list_experiments(verified=Depends(grant)):
        """Read experiments only with current administrator permission."""
        return experiments.list(verified[0])

    @router.put("/policy")
    def set_policy(body: PolicyRequest, verified=Depends(grant)):
        """Change a policy only with write consent, a live admin role and the current revision."""
        return policies.put(verified[0], body.config, body.revision, action="tool.updated")

    return router

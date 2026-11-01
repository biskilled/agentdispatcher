"""Independently deployable HTTP API over shared authentication and ledger services."""

import logging
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlparse
from uuid import UUID

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc.errors import JoseError
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from dispatcher.auth import AuthService, require_admin
from dispatcher.contracts import ApiConnection, ApiPlan, Contract, EventBatch, JobEvent, UsageEvent
from dispatcher.db import Database
from dispatcher.gateway import Gateway
from dispatcher.ledger import Ledger
from dispatcher.mail import Mailer
from dispatcher.membership import MembershipService
from dispatcher.operations_api import routes as operations_routes
from dispatcher.pricing import calculate_price
from dispatcher.reconciliation import Adjustment, ProviderSnapshot, Reconciliation
from dispatcher.reporting import Reporter, UsageFilter
from dispatcher.settings import Settings, get_settings

SESSION_COOKIE = "dispatcher_session"


def ledger_response(data) -> JSONResponse:
    """Preserve decimal precision across the JSON boundary using strings."""
    return JSONResponse(jsonable_encoder(data, custom_encoder={Decimal: str}))


class EmailRequest(Contract):
    """Basic email syntax; actual ownership is proven by the emailed token."""

    email: str = Field(pattern=r"^[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+$", max_length=254)


class LoginToken(Contract):
    """A single-use emailed bearer token."""

    token: str = Field(min_length=32, max_length=256)


class KeyRequest(Contract):
    """Every issued service credential has a concrete app and environment scope."""

    name: str = Field(min_length=1, max_length=100)
    app: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=50)


class InviteRequest(EmailRequest):
    """An invitation grants only the explicitly selected tenant role."""

    role: Literal["owner", "admin", "member", "viewer"] = "member"


class MemberRequest(Contract):
    """Set a member's role and exact list of app views; null role removes membership."""

    role: Literal["owner", "admin", "member", "viewer"] | None
    apps: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=100
    )


class DelegationRequest(Contract):
    """Bind user attribution consent to a named application."""

    app: str = Field(min_length=1, max_length=100)


class ConnectionRequest(Contract):
    """Optimistic configuration mutation; zero revision means create."""

    config: ApiConnection
    revision: int = Field(default=0, ge=0)


class PricePreview(Contract):
    """Synthetic preview inputs use the same validated formula as ingestion."""

    plan: ApiPlan
    event: UsageEvent
    previous_units: Decimal = Field(default=Decimal(0), ge=0, allow_inf_nan=False)


class GatewayKeyRequest(KeyRequest):
    """A virtual key explicitly permits a bounded set of model aliases."""

    models: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        min_length=1, max_length=100
    )


class GatewayAuthorization(Contract):
    """Trusted proxy middleware supplies the registered key ID and requested alias."""

    service_id: UUID
    model: str = Field(min_length=1, max_length=100)


class GatewayObservation(Contract):
    """A proxy attempt is scoped by its registered key, never by client telemetry tags."""

    service_id: UUID
    event: UsageEvent


def create_app(settings: Settings | None = None, mailer=None, oauth_transport=None) -> FastAPI:
    """Construct a service with explicit dependencies for production and integration tests."""
    settings = settings or get_settings()
    db = Database(settings)
    auth, ledger = AuthService(db), Ledger(db)
    reporter = Reporter(db)
    reconciliation = Reconciliation(db)
    gateway = Gateway(db)
    memberships = MembershipService(auth)
    mailer = mailer or Mailer(settings)
    app = FastAPI(title="AgentDispatcher", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.auth, app.state.ledger = auth, ledger
    app.state.gateway = gateway
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie="dispatcher_oauth",
        https_only=settings.secure_cookies,
        same_site="lax",
        max_age=settings.login_seconds,
    )
    oauth = OAuth()
    if settings.google_client_id:
        oauth.register(
            "google",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret.get_secret_value(),
            server_metadata_url=settings.google_metadata_url,
            client_kwargs={
                "scope": "openid email profile",
                "code_challenge_method": "S256",
                **({"transport": oauth_transport} if oauth_transport else {}),
            },
        )

    @app.middleware("http")
    async def response_policy(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def check_origin(request: Request):
        if request.headers.get("origin") != settings.public_url.rstrip("/"):
            raise HTTPException(403, "Request origin does not match this installation")

    def human(request: Request, tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")]):
        if request.method not in {"GET", "HEAD"}:
            check_origin(request)
        return auth.human(request.cookies.get(SESSION_COOKIE, ""), tenant_id)

    def service(
        authorization: Annotated[str, Header()],
        delegation: Annotated[str | None, Header(alias="X-User-Delegation")] = None,
    ):
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Bearer SDK key required")
        principal = auth.service(token)
        return auth.delegated(principal, delegation) if delegation else principal

    def gateway_callback(secret: Annotated[str, Header(alias="X-Gateway-Secret")]):
        gateway.verify_callback(secret)

    def set_session(response: Response, token: str):
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            max_age=settings.session_seconds,
            path="/",
        )

    @app.get("/health/live")
    def live():
        """Liveness does not disclose connection configuration."""
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        """Report readiness only after migrations are visible."""
        try:
            if db.ready():
                return {"status": "ready"}
        except Exception:
            logging.error("Database readiness check failed")
        return JSONResponse({"status": "unavailable"}, status_code=503)

    @app.get("/api/auth/providers")
    def providers():
        """Expose configured login methods without exposing secrets."""
        return {"google": bool(settings.google_client_id), "email": bool(settings.smtp_host)}

    @app.post("/api/auth/email/request", status_code=202)
    def email_request(body: EmailRequest, request: Request):
        """Issue generic responses for existing and unknown email identities."""
        check_origin(request)
        if not settings.smtp_host:
            raise HTTPException(503, "Email sign-in is not configured")
        token = auth.request_login(
            body.email.lower(), request.client.host if request.client else ""
        )
        if token:
            try:
                mailer.send_login(body.email.lower(), token)
            except Exception:
                # Avoid disclosing account existence or a bearer link in transport errors.
                logging.error("Login email delivery failed; check SMTP configuration")
        return {"message": "If this email has access, a sign-in link will arrive shortly."}

    @app.post("/api/auth/email/consume")
    def email_consume(body: LoginToken, request: Request, response: Response):
        """Require explicit user action; fetching the email link cannot consume it."""
        check_origin(request)
        set_session(response, auth.consume_login(body.token))
        return {"authenticated": True}

    @app.get("/api/auth/me")
    def me(request: Request):
        """Return current user and current memberships, not cached token claims."""
        return auth.user(request.cookies.get(SESSION_COOKIE, ""))

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, response: Response):
        """Revoke the browser session before clearing its cookie."""
        check_origin(request)
        auth.logout(request.cookies.get(SESSION_COOKIE, ""))
        response.delete_cookie(SESSION_COOKIE)

    @app.get("/api/auth/google/start")
    async def google_start(request: Request):
        """Start a library-managed state/nonce/PKCE flow."""
        if not settings.google_client_id:
            raise HTTPException(503, "Google sign-in is not configured")
        request.session.pop("link_user", None)
        redirect = await oauth.google.authorize_redirect(
            request, settings.public_url.rstrip("/") + "/api/auth/google/callback"
        )
        await persist_oidc(redirect)
        return redirect

    async def persist_oidc(redirect):
        state = parse_qs(urlparse(redirect.headers["location"]).query)["state"][0]
        await run_in_threadpool(auth.start_oidc, state)

    @app.post("/api/auth/google/link")
    async def google_link(request: Request):
        """Explicitly bind a new Google identity to the currently authenticated account."""
        check_origin(request)
        if not settings.google_client_id:
            raise HTTPException(503, "Google sign-in is not configured")
        user = await run_in_threadpool(auth.recent_user, request.cookies.get(SESSION_COOKIE, ""))
        request.session["link_user"] = str(user["user_id"])
        redirect = await oauth.google.authorize_redirect(
            request,
            settings.public_url.rstrip("/") + "/api/auth/google/callback",
            prompt="select_account",
        )
        await persist_oidc(redirect)
        return {"url": redirect.headers["location"]}

    @app.get("/api/auth/google/callback")
    async def google_callback(request: Request):
        """Only validated OIDC claims reach account lookup; never log callback secrets."""
        if not settings.google_client_id:
            raise HTTPException(503, "Google sign-in is not configured")
        await run_in_threadpool(auth.consume_oidc, request.query_params.get("state", ""))
        try:
            token = await oauth.google.authorize_access_token(request)
        except (OAuthError, JoseError, ValueError):
            raise HTTPException(401, "Google sign-in could not be verified") from None
        if not token.get("userinfo"):
            raise HTTPException(401, "Verified identity token required")
        link = request.session.pop("link_user", None)
        if link:
            current = await run_in_threadpool(
                auth.recent_user, request.cookies.get(SESSION_COOKIE, "")
            )
            if str(current["user_id"]) != link:
                raise HTTPException(401, "Account-linking session changed")
        session = await run_in_threadpool(
            auth.google_login, token["userinfo"], UUID(link) if link else None
        )
        await run_in_threadpool(auth.logout, request.cookies.get(SESSION_COOKIE, ""))
        request.session.clear()
        response = RedirectResponse(settings.public_url)
        set_session(response, session)
        return response

    @app.get("/api/members")
    def members(principal=Depends(human)):
        """List tenant roles and granted app views."""
        return memberships.members(principal)

    @app.put("/api/members/{user_id}", status_code=204)
    def update_member(user_id: UUID, body: MemberRequest, principal=Depends(human)):
        """Change permissions without allowing removal of the last owner."""
        memberships.update(principal, user_id, body.role, body.apps)

    @app.get("/api/invitations")
    def invitations(principal=Depends(human)):
        """Return invitation status without token verifiers."""
        return memberships.invitations(principal)

    @app.post("/api/invitations", status_code=201)
    def invite(body: InviteRequest, principal=Depends(human)):
        """Create a one-time invitation; accepting also requires independent sign-in."""
        return memberships.invite(principal, body.email.lower(), body.role)

    @app.delete("/api/invitations/{invite_id}", status_code=204)
    def revoke_invite(invite_id: UUID, principal=Depends(human)):
        """Cancel an outstanding tenant invitation."""
        memberships.revoke(principal, invite_id)

    @app.post("/api/invitations/accept")
    def accept_invite(body: LoginToken, request: Request):
        """Join a tenant only after proving control of the invited account."""
        check_origin(request)
        return memberships.accept(auth.user(request.cookies.get(SESSION_COOKIE, "")), body.token)

    @app.post("/api/auth/delegate", status_code=201)
    def delegate(body: DelegationRequest, request: Request, principal=Depends(human)):
        """Issue scoped user attribution consent for an application request."""
        return auth.delegate(request.cookies.get(SESSION_COOKIE, ""), principal.tenant_id, body.app)

    @app.get("/api/keys")
    def keys(principal=Depends(human)):
        """List metadata for the tenant's keys."""
        return auth.keys(principal)

    @app.post("/api/keys", status_code=201)
    def issue_key(body: KeyRequest, principal=Depends(human)):
        """Issue a scoped key; this is the only response containing its secret."""
        return auth.issue_key(principal, body.name, body.app, body.environment)

    @app.delete("/api/keys/{key_id}", status_code=204)
    def revoke_key(key_id: UUID, principal=Depends(human)):
        """Revoke a key without accepting a caller-controlled tenant lookup."""
        auth.revoke_key(principal, key_id)

    @app.post("/api/ingest", status_code=202)
    def ingest(body: EventBatch, principal=Depends(service)):
        """Accept one atomic batch of metadata from an authenticated SDK."""
        if len(body.events) > settings.request_limit:
            raise HTTPException(413, "Batch exceeds configured limit")
        return ledger.ingest(principal, body.events)

    @app.post("/api/jobs/events", status_code=202)
    def job_event(body: JobEvent, principal=Depends(service)):
        """Record an authenticated scheduler/worker transition."""
        ledger.job(principal, body)
        return {"accepted": True}

    @app.get("/api/overview")
    def overview(filters: Annotated[UsageFilter, Query()], principal=Depends(human)):
        """Read authoritative totals, keeping currency and cost kinds separate."""
        return ledger_response(reporter.overview(principal, filters))

    @app.get("/api/events")
    def events(
        filters: Annotated[UsageFilter, Query()],
        principal=Depends(human),
    ):
        """Page through tenant usage without exposing unbounded result sets."""
        return ledger_response(reporter.events(principal, filters))

    @app.get("/api/events/{event_id}")
    def event_detail(event_id: UUID, principal=Depends(human)):
        """Expose original attempt evidence only within the caller's usage views."""
        return ledger_response(reporter.event(principal, event_id))

    @app.get("/api/jobs")
    def jobs(principal=Depends(human)):
        """Read recent job state and coverage hints."""
        return ledger.jobs(principal)

    @app.get("/api/plans")
    def plans(principal=Depends(human)):
        """Read the API catalog's immutable pricing versions."""
        return ledger.plans(principal)

    @app.post("/api/plans", status_code=201)
    def plan(body: ApiPlan, principal=Depends(human)):
        """Publish an explicit free, unknown or per-unit pricing version."""
        return ledger.add_plan(principal, body)

    @app.post("/api/plans/preview")
    def preview(body: PricePreview, principal=Depends(human)):
        """Calculate a synthetic marginal price without publishing a plan or billing an event."""
        require_admin(principal)
        cost, currency, kind = calculate_price(body.plan, body.event, body.previous_units)
        return ledger_response(
            {
                "cost": cost,
                "currency": currency,
                "cost_kind": kind,
                "fixed_fee_per_period": body.plan.fixed_fee,
            }
        )

    @app.get("/api/connections")
    def connections(principal=Depends(human)):
        """Read configured API/account pools without disclosing credentials."""
        return ledger.accounting.connections(principal)

    @app.put("/api/connections")
    def connection(body: ConnectionRequest, principal=Depends(human)):
        """Create or revise one connection under optimistic concurrency."""
        return ledger.accounting.put_connection(principal, body.config, body.revision)

    @app.get("/api/quotas")
    def quotas(principal=Depends(human)):
        """Show observed allowance consumption, including unknown-count uncertainty."""
        return ledger_response(ledger.accounting.quotas(principal))

    @app.get("/api/charges")
    def charges(principal=Depends(human)):
        """List account-level subscription fees separately from usage cost."""
        return ledger_response(ledger.accounting.charges(principal))

    @app.get("/api/alerts")
    def alerts(principal=Depends(human)):
        """Read persisted threshold notifications without triggering external messages."""
        return ledger_response(ledger.accounting.alerts(principal))

    @app.get("/api/reconciliation")
    def reconcile(principal=Depends(human)):
        """Compare provider statements with observed usage without adding invoice totals."""
        return ledger_response(reconciliation.reports(principal))

    @app.post("/api/reconciliation", status_code=201)
    def snapshot(body: ProviderSnapshot, principal=Depends(human)):
        """Record a provider statement with source and freshness evidence."""
        return reconciliation.import_snapshot(principal, body)

    @app.get("/api/adjustments")
    def adjustments(principal=Depends(human)):
        """Read separate refund/correction entries."""
        return ledger_response(reconciliation.adjustments(principal))

    @app.post("/api/adjustments", status_code=201)
    def adjustment(body: Adjustment, principal=Depends(human)):
        """Append an audited correction to an existing tenant event."""
        return reconciliation.adjust(principal, body)

    @app.get("/api/gateway/keys")
    def gateway_keys(principal=Depends(human)):
        """List distinct LLM virtual keys for this tenant."""
        return gateway.keys(principal)

    @app.post("/api/gateway/keys", status_code=201)
    def gateway_key(body: GatewayKeyRequest, principal=Depends(human)):
        """Issue a model-restricted LiteLLM key once; never expose the gateway master key."""
        return gateway.issue(principal, body.name, body.app, body.environment, body.models)

    @app.post("/internal/gateway/authorize", dependencies=[Depends(gateway_callback)])
    def gateway_authorize(body: GatewayAuthorization):
        """Deny upstream LLM execution for unknown, revoked or out-of-policy keys."""
        principal = gateway.principal(body.service_id, body.model)
        return {
            "service_id": principal.subject_id,
            "app": principal.app,
            "environment": principal.environment,
        }

    @app.post("/internal/gateway/ingest", status_code=202, dependencies=[Depends(gateway_callback)])
    def gateway_ingest(body: GatewayObservation):
        """Store one proxy observation; its reported cost is gateway-calculated, not invoiced."""
        return ledger.ingest(gateway.principal(body.service_id), [body.event])

    app.include_router(operations_routes(ledger.operations, human))
    return app

"""Independently deployable HTTP API over shared authentication and ledger services."""

import logging
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from dispatcher.auth import AuthService
from dispatcher.contracts import ApiPlan, Contract, EventBatch, JobEvent
from dispatcher.db import Database
from dispatcher.ledger import Ledger
from dispatcher.mail import Mailer
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


def create_app(settings: Settings | None = None, mailer=None) -> FastAPI:
    """Construct a service with explicit dependencies for production and integration tests."""
    settings = settings or get_settings()
    db = Database(settings)
    auth, ledger = AuthService(db), Ledger(db)
    mailer = mailer or Mailer(settings)
    app = FastAPI(title="AgentDispatcher", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.auth, app.state.ledger = auth, ledger
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
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
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

    def service(authorization: Annotated[str, Header()]):
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Bearer SDK key required")
        return auth.service(token)

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
        return await oauth.google.authorize_redirect(
            request, settings.public_url.rstrip("/") + "/api/auth/google/callback"
        )

    @app.post("/api/auth/google/link")
    async def google_link(request: Request):
        """Explicitly bind a new Google identity to the currently authenticated account."""
        check_origin(request)
        if not settings.google_client_id:
            raise HTTPException(503, "Google sign-in is not configured")
        user = await run_in_threadpool(auth.user, request.cookies.get(SESSION_COOKIE, ""))
        request.session["link_user"] = str(user["user_id"])
        redirect = await oauth.google.authorize_redirect(
            request,
            settings.public_url.rstrip("/") + "/api/auth/google/callback",
            prompt="select_account",
        )
        return {"url": redirect.headers["location"]}

    @app.get("/api/auth/google/callback")
    async def google_callback(request: Request):
        """Only validated OIDC claims reach account lookup; never log callback secrets."""
        if not settings.google_client_id:
            raise HTTPException(503, "Google sign-in is not configured")
        try:
            token = await oauth.google.authorize_access_token(request)
        except OAuthError:
            raise HTTPException(401, "Google sign-in could not be verified") from None
        link = request.session.pop("link_user", None)
        if link:
            current = await run_in_threadpool(auth.user, request.cookies.get(SESSION_COOKIE, ""))
            if str(current["user_id"]) != link:
                raise HTTPException(401, "Account-linking session changed")
        session = await run_in_threadpool(
            auth.google_login, token["userinfo"], UUID(link) if link else None
        )
        request.session.clear()
        response = RedirectResponse(settings.public_url)
        set_session(response, session)
        return response

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
    def overview(app_name: str | None = None, principal=Depends(human)):
        """Read authoritative totals, keeping currency and cost kinds separate."""
        return ledger_response(ledger.overview(principal, app_name))

    @app.get("/api/events")
    def events(
        offset: Annotated[int, Query(ge=0)] = 0,
        app_name: str | None = None,
        principal=Depends(human),
    ):
        """Page through tenant usage without exposing unbounded result sets."""
        return ledger_response(ledger.events(principal, offset, app_name))

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

    return app

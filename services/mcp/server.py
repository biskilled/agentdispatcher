"""Optional MCP process: protocol handling comes from the official SDK, permissions from the API."""

import os
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx2
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import AnyHttpUrl


@dataclass(frozen=True)
class Settings:
    """Endpoint configuration is process-owned, never supplied by a model's tool arguments."""

    api_url: str
    timeout: float = 10
    resource_url: str = ""
    issuer_url: str = ""
    allow_http: bool = False

    @classmethod
    def from_env(cls):
        """Load explicit connection settings; missing endpoint configuration fails at startup."""
        return cls(
            api_url=os.environ["DISPATCHER_API_URL"],
            timeout=float(os.environ.get("DISPATCHER_MCP_TIMEOUT", "10")),
            resource_url=os.environ.get("DISPATCHER_MCP_RESOURCE_URL", ""),
            issuer_url=os.environ.get("DISPATCHER_MCP_ISSUER_URL", ""),
            allow_http=os.environ.get("DISPATCHER_MCP_ALLOW_HTTP", "false").lower() == "true",
        )

    def __post_init__(self):
        for url in (self.api_url, self.resource_url, self.issuer_url):
            if not url:
                continue
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"https", "http"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.fragment
                or parsed.query
            ):
                raise ValueError(
                    "MCP endpoints require HTTP(S) URLs without credentials or queries"
                )
            if parsed.scheme != "https" and not self.allow_http:
                raise ValueError(
                    "HTTP requires explicit DISPATCHER_MCP_ALLOW_HTTP for private/local networks"
                )
        if self.timeout <= 0:
            raise ValueError("MCP timeout must be positive")


def tenant_from_token(token):
    """Extract only a claimed tenant selector; the API still verifies the entire token hash."""
    parts = token.split("_", 2)
    if len(parts) != 3 or parts[0] != "dta":
        raise ToolError("A dedicated Dispatcher tool credential is required")
    try:
        return str(UUID(parts[1]))
    except ValueError as error:
        raise ToolError("Invalid Dispatcher tool credential") from error


class DispatcherAPI:
    """Reuse backend authorization on every invocation, without caching tokens or memberships."""

    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    async def call(self, token, path, *, method="GET", params=None, body=None):
        """Send credentials only to the configured backend; return no transport diagnostics."""
        tenant = tenant_from_token(token)
        try:
            async with httpx2.AsyncClient(
                base_url=self.settings.api_url.rstrip("/") + "/",
                timeout=self.settings.timeout,
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    method,
                    "api/tools/" + path,
                    params=params,
                    json=body,
                    headers={"Authorization": "Bearer " + token, "X-Tenant-ID": tenant},
                )
            if not response.is_success:
                raise ToolError(f"Dispatcher refused this operation (HTTP {response.status_code})")
            return response.json()
        except (httpx2.HTTPError, ValueError) as error:
            raise ToolError("Dispatcher is unavailable or returned an invalid response") from error


class TokenVerifier:
    """Introspect local grants and enforce the resource audience minted by Dispatcher."""

    def __init__(self, api):
        self.api = api

    async def verify_token(self, token):
        """Fail closed on expired sessions, removed memberships and wrong resource audiences."""
        try:
            identity = await self.api.call(token, "me")
            if identity["resource"] != self.api.settings.resource_url:
                return None
            return AccessToken(
                token=token,
                client_id=str(identity["user_id"]),
                subject=str(identity["user_id"]),
                resource=identity["resource"],
                scopes=["usage:read"] + (["policy:write"] if identity["can_write_policy"] else []),
                expires_at=int(datetime.fromisoformat(identity["expires_at"]).timestamp()),
                claims={"tenant_id": identity["tenant_id"]},
            )
        except (ToolError, KeyError, ValueError):
            return None


def create_server(settings, *, stdio_token=None, transport=None):
    """Construct one small server supporting per-user stdio or authenticated multi-user HTTP."""
    api = DispatcherAPI(settings, transport)
    arguments = {"subscriptions": False}
    if stdio_token is None:
        if not settings.resource_url or not settings.issuer_url:
            raise ValueError("HTTP MCP requires an explicit resource URL and issuer URL")
        arguments.update(
            token_verifier=TokenVerifier(api),
            auth=AuthSettings(
                issuer_url=AnyHttpUrl(settings.issuer_url),
                resource_server_url=AnyHttpUrl(settings.resource_url),
                required_scopes=["usage:read"],
                validate_token_resource=True,
            ),
        )
    server = MCPServer("AgentDispatcher", version="0.1.0", log_level="WARNING", **arguments)

    def credential():
        if stdio_token is not None:
            return stdio_token
        access = get_access_token()
        if access is None:
            raise ToolError("Authenticated Dispatcher tool access is required")
        return access.token

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    async def get_usage(filters: dict | None = None) -> dict:
        """Read permitted usage totals and breakdowns. Filters only narrow existing permission."""
        return await api.call(credential(), "usage", params=filters or {})

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    async def get_session(session_id: str) -> dict:
        """Read permitted work-item costs for one session; its ID never grants access."""
        return await api.call(credential(), "sessions/" + quote(session_id, safe=""))

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    async def list_experiments() -> dict:
        """List experiments in the authorized workspace; administrator permission is required."""
        return {"experiments": await api.call(credential(), "experiments")}

    @server.tool(
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=False
        )
    )
    async def set_policy(config: dict, revision: int) -> dict:
        """Activate a policy with explicit write consent, a live admin role and current revision."""
        return await api.call(
            credential(), "policy", method="PUT", body={"config": config, "revision": revision}
        )

    return server


def http_app(settings, transport=None):
    """Serve a stateless HTTP resource with exact Host/Origin checks and no shared human token."""
    resource = urlsplit(settings.resource_url)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[resource.netloc],
        allowed_origins=[f"{resource.scheme}://{resource.netloc}"],
    )
    return create_server(settings, transport=transport).streamable_http_app(
        streamable_http_path=resource.path or "/",
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )


def main():
    """Start the selected transport; credentials come from the launch environment."""
    settings = Settings.from_env()
    mode = os.environ.get("DISPATCHER_MCP_TRANSPORT", "stdio")
    if mode == "stdio":
        create_server(settings, stdio_token=os.environ["DISPATCHER_TOOLS_TOKEN"]).run()
    elif mode == "http":
        import uvicorn

        uvicorn.run(
            http_app(settings),
            host=os.environ["DISPATCHER_MCP_HOST"],
            port=int(os.environ["DISPATCHER_MCP_PORT"]),
            access_log=False,
        )
    else:
        raise ValueError("DISPATCHER_MCP_TRANSPORT must be stdio or http")


if __name__ == "__main__":
    main()

# Optional AgentDispatcher MCP service

This separately deployable Python process uses the official MIT-licensed
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk). It supports stdio
and stateless Streamable HTTP. The API, React UI and application monitoring SDK do not
need these dependencies. Install the pinned `requirements.lock` into an isolated
Python 3.12+ environment. On this organization's workstations, environments live under
`/Users/user/Documents/venv`.

The four tools call the same backend reporting and policy services as the browser:

| Tool | Permission |
| --- | --- |
| `get_usage(filters)` | The user's existing tenant, app-view and own-usage permissions |
| `get_session(session_id)` | The same restrictions, narrowed to one session |
| `list_experiments()` | Current tenant owner/admin |
| `set_policy(config, revision)` | Current owner/admin plus explicit policy-write consent |

There are no credentials or tenant selectors in the model-visible tool arguments.
The process extracts a claimed tenant ID from the credential, then the API verifies
the hash of the entire credential and its actual tenant, human session, membership
and grants. Changing that prefix does not change authorization. Each invocation
rechecks backend permissions; tools do not cache membership or token validity.

## Create access

Sign in through Dispatcher using email or Google, select the workspace, and open
**Tool access**. Create a read-only credential, or explicitly allow model policy
changes as an administrator. Store the one-time secret in the MCP client's secret
environment. It expires after `DISPATCHER_TOOL_TOKEN_SECONDS` (default one hour,
maximum one day), or earlier when its browser session expires, signs out, loses
membership or revokes the grant. A role downgrade immediately stops policy writes.
Only the credential hash is stored in PostgreSQL. SDK and LiteLLM keys are not accepted.

## Local stdio client

Configure the MCP host to execute the service environment's Python with
`services/mcp/server.py` as the script. Set these process environment variables:

- `DISPATCHER_API_URL`: the Dispatcher API/UI origin.
- `DISPATCHER_TOOLS_TOKEN`: the dedicated tool credential from the secret store.
- `DISPATCHER_MCP_TRANSPORT=stdio` (the default).
- `DISPATCHER_MCP_ALLOW_HTTP=true` only for an intentionally private/local HTTP endpoint.

The endpoint and token come from the launcher, not prompts or tool arguments. The
SDK handles protocol framing. No browser extension or desktop shell is required to
use the monitoring dashboard on macOS, Windows or mobile.

## Separate HTTP service

Set `DISPATCHER_TOOL_RESOURCE_URL` in the API/Compose environment to the exact public
MCP endpoint URL, including its path, before issuing credentials. A local example is
`http://127.0.0.1:8090/mcp`; remote installations use HTTPS. Recreate the API when
changing this setting. Existing credentials retain their original audience.

Run `docker compose --profile mcp up --build -d api mcp`. `MCP_HOST`, `MCP_PORT` and
`PUBLIC_HOST` control the listener; it publishes on loopback by default. HTTP clients
send their own tool credential in `Authorization: Bearer …`. No shared human token
is configured on the server. Tokens for another resource URL are rejected. Behind
a reverse proxy, preserve the public Host header; the server permits only the
configured resource host and origin. The Compose service uses private HTTP to the
API; terminate remote TLS at your deployment boundary.

For deployment without Compose, set `DISPATCHER_MCP_TRANSPORT=http`,
`DISPATCHER_API_URL`, `DISPATCHER_MCP_RESOURCE_URL`, `DISPATCHER_MCP_ISSUER_URL`,
`DISPATCHER_MCP_HOST` and `DISPATCHER_MCP_PORT`. The resource URL must match the audience
configured in the API. The issuer is the Dispatcher installation that issues grants.

The current connection method is a manually provisioned bearer grant. The SDK serves
protected-resource metadata; Dispatcher does not yet implement an OAuth authorization
server for automatic MCP-client login/discovery. Configure the client with its explicit
bearer header. Google/email login and consent happen in the Dispatcher browser UI.

## Verification and scope

`python services/mcp/test_server.py` runs actual SDK in-process and HTTP transport
checks in this environment. `scripts/mcp_smoke.py`, run inside the API container by
CI, exercises the separate MCP container, real PostgreSQL, two tenants, credential
tampering and immediate logout. Core PostgreSQL tests cover write consent, role
changes, hash-only storage, revoked grants and expiry.

This service exposes monitoring/governance tools. It is distinct from instrumenting
or proxying arbitrary third-party MCP calls; that monitoring adapter remains tracked
separately. Runtime licenses are preserved in `third_party/notices.json` here and
included in the application's combined licenses screen.

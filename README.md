# AgentDispatcher

React monitoring for application API calls, LLM requests and scheduled work, backed by a tenant-isolated PostgreSQL ledger. One repository contains independently runnable API, worker, UI and Python SDK packages.

**Development preview:** the first monitoring flow works. This is not yet the complete approved US10000 use case or a production release. See [implementation status](documents/output/implementation-progress.md) for implemented, verified and outstanding work.

## Try the synthetic demo

Requires Python 3.12+ to generate configuration and Docker with Compose v2. Images/dependencies need downloading on first build; the running demo makes no external provider calls and requires no paid account.

```sh
python3 scripts/configure.py
docker compose up --build -d
docker compose --profile demo run --rm demo
```

Open the short-lived `sign_in` link printed by the demo command and click **Continue to workspace**. The workspace contains 18 synthetic attempts across three applications, including deliberately unknown LLM prices. Rates are fixtures, not actual vendor prices. The demo creates its own tenant and does not change existing tenant data. Repeating the command reuses the seeded workspace and issues a new login link, subject to throttling.

The UI binds to `127.0.0.1:8088` by default. Change `UI_PORT` and `DISPATCHER_PUBLIC_URL` together in `.env`. PostgreSQL, API, gateway and collector have no published management ports. Data survives service/container restarts in the `database` volume. Do not remove that volume if you need the data.

**Verification note:** local PostgreSQL/API/SDK/browser tests passed. [GitHub CI](https://github.com/biskilled/agentdispatcher/actions/runs/41299724331) also passed the application checks, Compose build/startup, synthetic demo, worker restart and API readiness check. Docker is unavailable on the local development machine; container verification ran on the CI runner. Optional gateway/collector profiles and database backup/restore remain unverified.

## Create a real workspace

Configure SMTP in `.env`, then provision the initial owner from the operator CLI:

```sh
docker compose exec api dispatcher create-tenant --name "My workspace" --email "owner@example.com"
```

The email address alone is not proof of identity. The owner signs in using a single-use email link before receiving dashboard access. Public self-service tenant creation and invitation management are still pending.

For Google sign-in, configure `DISPATCHER_GOOGLE_CLIENT_ID` and `DISPATCHER_GOOGLE_CLIENT_SECRET`. Register the exact `${DISPATCHER_PUBLIC_URL}/api/auth/google/callback` redirect URI in Google. Accounts use the OIDC issuer and subject; matching email addresses are **not** automatically linked. An authenticated client can explicitly initiate linking using `POST /api/auth/google/link`; the dedicated account-management UI is still pending. A newly created Google account has no workspace access until membership is provisioned.

For remote/mobile access, put the UI behind HTTPS, set `DISPATCHER_PUBLIC_URL` to that origin, enable `DISPATCHER_SECURE_COOKIES=true`, and configure the listen address/reverse proxy intentionally. The React application runs in desktop and mobile browsers; no desktop app is needed.

## Instrument an application

Install only the small SDK into your application's environment:

```sh
pip install ./packages/sdk
```

Create a tenant key in **SDK keys**, scoped to the application's name and environment. Store it in the application's environment or secret store; never in browser code, prompts or YAML committed to Git.

```python
import os
from agentdispatcher_sdk import Monitor

monitor = Monitor(
    endpoint=os.environ["DISPATCHER_ENDPOINT"],
    key=os.environ["DISPATCHER_SDK_KEY"],
    app=os.environ["APPLICATION_NAME"],
    environment=os.environ["APPLICATION_ENVIRONMENT"],
)

with monitor.job("scheduled-analysis"):
    with monitor.operation(provider="market-data", operation="price", api_id="market-data") as usage:
        response = existing_http_client.get(configured_provider_url)
        usage["status_code"] = response.status_code
        response.raise_for_status()

# At application shutdown, not after each request:
flushed = monitor.close()
```

Wrap each physical request attempt, including each retry/page. Reuse `operation_id` for a shared logical operation. Use `monitor.record(resource_kind="llm", ...)` for measured provider token counts. Use `heartbeat()` for long-running jobs. The SDK carries current OpenTelemetry trace IDs when available and separates concurrent job contexts. Queue/process propagation and gateway correlation adapters remain pending.

Export runs in a bounded background queue. Delivery retries retain event IDs; business requests are never retried by the monitoring SDK. `delivered`, `failed`, `dropped` and the result of `close()` expose loss. Abrupt process termination can lose queued telemetry. HTTP hooks and additional language SDKs are not yet provided.

## Accounting and security boundaries

- Runtime PostgreSQL roles cannot bypass RLS. Tenant context is transaction-local and comes from authenticated credentials. A separate narrowly granted auth connection owns identity, membership and credential lookups; no public route exposes those tables directly.
- Human access and service ingestion are separate. SDK keys cannot read reports or administer tenants. Key verifiers are SHA-256 hashes of high-entropy random secrets; secrets are shown once. Expiry/revocation and membership changes are checked on each request.
- Owner/admin can see tenant-wide usage. Member/viewer access is denied until explicit view grants are implemented; role names alone do not expose tenant data.
- Identical event replays are idempotent; altered evidence with the same event/attempt ID is rejected. Separate SDK/gateway representations need the forthcoming correlation adapter and must not be blindly submitted with different attempt IDs.
- Only explicit unknown/free/per-unit pricing is implemented. Historic events keep their plan version. Monetary values are PostgreSQL decimals and JSON strings. SDK actor IDs are app-reported, not authenticated human identities.
- Quota fields are stored but quota evaluation, thresholds, subscription/tier allocation and provider reconciliation are pending. Current monitoring is not hard quota enforcement.
- No request/response body fields exist in the ingestion contract. Unknown fields are rejected. Applications must still avoid putting secrets in allowed labels. OIDC access logging is disabled in the provided server/proxy configuration.

## Services and optional integrations

| Component | Entrypoint | State |
| --- | --- | --- |
| API | `uvicorn dispatcher.api:create_app --factory` | Auth, catalog, intake and monitoring reads |
| Worker | `dispatcher-worker` | Tenant-scoped stale-run detection and heartbeat |
| UI | `npm run dev` / static Vite build | Desktop/mobile monitoring and administration |
| Migrations | `python scripts/migrate.py` | Sole schema owner, separate deployment credentials |
| LiteLLM | Compose `gateway` profile | Main planned LLM gateway; adapter integration pending |
| OTel collector | Compose `telemetry` profile | Private diagnostic receiver; ledger export pending |

`docker compose --profile gateway up -d gateway` starts the configured LiteLLM image after you supply `LLM_PROVIDER_MODEL` and `LLM_API_KEY`. It is internal-only. Its master key is an operator credential and must not be used as a tenant SDK key. Automatic virtual-key provisioning, model policy integration, billing correlation and live provider verification are still open work. OpenRouter can later be configured as a LiteLLM upstream.

The collector's debug exporter reports basic diagnostics, not durable usage; it does not feed the ledger. Do not expose it publicly or count it as complete OTel ingestion coverage.

## Development and verification

Use Python 3.12+ and Node 24. Install the runtime lock, then the project and development tools. On this organisation's workstations, `.venv` and `node_modules` must be symlinks into `/Users/user/Documents/venv` and `/Users/user/Documents/node_modules`; install npm dependencies at the shared destination with `npm ci --prefix ...` so npm does not replace the symlink.

```sh
python -m pip install -r requirements.lock
python -m pip install -e '.[dev]'
npm ci
ruff check packages scripts tests
pytest -q
npm run build
python scripts/notices.py
```

Integration tests require `TEST_DATABASE_URL` pointing to a **disposable PostgreSQL owner database**. They create application roles/schema and synthetic tenants. Without it, PostgreSQL tests skip; skipped tests are not proof of isolation. CI supplies one. SDK tests run without a database.

For local browser tests, run API/UI against the same database with a private environment file containing the `DISPATCHER_*` settings, `DISPATCHER_DEMO_ENDPOINT`, `UI_PORT` and `BACKEND_URL`. Then:

```sh
python scripts/verify_local.py --env-file /path/to/private-local.env
```

This seeds synthetic data through the real SDK, checks desktop/mobile screens with Playwright, and revokes its temporary browser session. It never puts the session secret in command-line arguments. Install Playwright Chromium if not already available.

## Built on

Thanks to the maintainers of FastAPI, Starlette, Pydantic, Psycopg/PostgreSQL, Authlib, HTTPX, OpenTelemetry, React, Vite, Lucide, LiteLLM and the other dependencies that make this project possible. AgentDispatcher is Apache-2.0; dependencies retain their own terms, including Psycopg's LGPL terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), the generated [runtime notices](third_party/notices.json), and **Open-source licenses** in the UI. No QuotaBar or CodexBar code has been copied into this implementation.

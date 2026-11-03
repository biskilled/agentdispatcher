# Railway deployment

Project: [dispatcher](https://railway.com/project/ec055b41-12f2-4f02-b5a9-ae3de6d152e5), environment `production`.

Dashboard: https://agentdispatcher-production.up.railway.app

Authenticated MCP resource: https://mcp-production-5562.up.railway.app/mcp

The dashboard resolves the API hostname again as its DNS cache expires, using the container resolver and IPv4 records. This supports replacing the API without restarting the dashboard.

The dashboard serves the React build and proxies `/api/` to the private API. SDK clients use the dashboard URL as their endpoint. Database, worker, gateway, collector and operator jobs have no public domain or TCP proxy. MCP requires a dedicated session-bound tool token; an SDK ingestion key does not authorize MCP tools.

## Services

All builds use the repository root as their context and the `DOCKERFILE` builder. Base-image/build arguments come from `.env.example`, supplied as Railway variables. Railway does not run `compose.yaml` or provide its bind mounts: collector and gateway configuration are copied into their images.

| Service | Dockerfile | Start command / settings |
| --- | --- | --- |
| `postgres` | `services/postgres/Dockerfile` | Image default; persistent volume `/var/lib/postgresql/data`; `PGDATA=/var/lib/postgresql/data/pgdata` |
| `migrate` | `services/api/Dockerfile` | `python scripts/migrate.py`; restart `NEVER` |
| `api` | `services/api/Dockerfile` | `python scripts/start_service.py api`; `API_HOST=0.0.0.0`, `PORT=8080`; readiness `/health/ready` |
| `worker` | `services/api/Dockerfile` | `python scripts/start_service.py worker`; verify with `dispatcher-worker --health` |
| `agentdispatcher` | `services/ui/Dockerfile` | Image default; `PORT=80`; `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`, `BACKEND_DNS_IPV6=off`, `BACKEND_DNS_VALID_SECONDS=10`; public target port 80; readiness `/health/ready` |
| `gateway` | `services/gateway/Dockerfile` | `python /app/start.py`; `GATEWAY_HOST=0.0.0.0`, `PORT=4000`; health `/health/liveliness` |
| `collector` | `services/collector/Dockerfile` | Image default; `OTEL_HTTP_ENDPOINT=[::]:4318`, `OTEL_HEALTH_ENDPOINT=[::]:13133` |
| `mcp` | `services/mcp/Dockerfile` | Image default; `DISPATCHER_MCP_TRANSPORT=http`, `DISPATCHER_MCP_HOST=0.0.0.0`, `DISPATCHER_MCP_PORT=8090`, `PORT=8090` |
| `recovery` | `services/api/Dockerfile` | `python -m dispatcher.recovery backup /backups/dispatcher-initial.dump`; `INSTALL_POSTGRES_CLIENT=true`, `RAILWAY_RUN_UID=0`; volume `/backups`; restart `NEVER` |

`migrate` and `recovery` exit successfully after their job. Zero running replicas for those jobs is expected. The initial backup command refuses to overwrite an existing archive; choose a new destination for each later backup. No recurring backup schedule is implied by this one-shot service.

Railway's [start command](https://docs.railway.com/deployments/start-command) overrides the Docker entrypoint. Its [volume documentation](https://docs.railway.com/volumes/reference) documents `RAILWAY_RUN_UID=0` for the operator job's mounted volume. API and worker continue to run as the image's unprivileged user.

## Database and pgvector

The database uses PostgreSQL 17.11 and builds pgvector 0.8.7 from the versioned upstream archive. The Docker build checks its SHA-256 before compilation. `PGVECTOR_SOURCE_URL` and `PGVECTOR_SHA256` are required build variables; changing the version requires updating the URL, checksum and attribution together. Compiler packages stay in the builder stage.

New databases run `CREATE EXTENSION IF NOT EXISTS vector` during initialization. An existing PostgreSQL data volume is never reinitialized; after installing the extension files, an operator enables it separately in each existing database that needs it:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
SELECT '[1,2]'::vector <-> '[1,2]'::vector AS distance;
```

Vector support is available for future features. The current usage ledger does not generate embeddings or incur embedding API charges. Tenant isolation remains the responsibility of the application's row security policies for any future vector tables.

## Variables and credentials

`.env.example` is the complete baseline for application settings. Do not upload a local `.env` or give owner database credentials to runtime services. The deployment uses separate random credentials for these scopes:

- `postgres`: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `PGDATA`, and the three PostgreSQL/pgvector build variables.
- `migrate` only: `DISPATCHER_MIGRATION_DATABASE_URL`, `DISPATCHER_APP_DB_PASSWORD`, `DISPATCHER_AUTH_DB_PASSWORD`, `DISPATCHER_GATEWAY_DB_PASSWORD`.
- `api` and `worker`: `DISPATCHER_DATABASE_URL` authenticates as `dispatcher_app`; `DISPATCHER_AUTH_DATABASE_URL` as `dispatcher_auth`. Both get `DISPATCHER_SESSION_SECRET`, `DISPATCHER_PUBLIC_URL`, `DISPATCHER_SECURE_COOKIES=true`, `DISPATCHER_CONFIG_SOURCES={}` and the normal limits/timing variables from `.env.example`.
- `gateway`: `LITELLM_DATABASE_URL` authenticates as `dispatcher_gateway` with `?schema=litellm`; `LITELLM_MASTER_KEY`, `DISPATCHER_GATEWAY_CALLBACK_SECRET`, `DISPATCHER_CALLBACK_URL`; `GATEWAY_CONFIG_PATH=/app/config.yaml`, `GATEWAY_LAUNCHER=/app/docker/prod_entrypoint.sh`.
- `api`: matching `DISPATCHER_GATEWAY_MASTER_KEY` and `DISPATCHER_GATEWAY_CALLBACK_SECRET`, plus `DISPATCHER_GATEWAY_URL` and `DISPATCHER_TOOL_RESOURCE_URL`.
- `collector`: its own `DISPATCHER_COLLECTOR_TOKEN` for inbound OTLP, and `DISPATCHER_OTLP_SDK_KEY` for backend ingestion. The SDK key is scoped to a single tenant, application and environment. Separate app/environment collectors need separate keys. Rotate before the key's expiry (90 days by default).
- `recovery` only: `DISPATCHER_RECOVERY_DATABASE_URL` with operator access.

Database DSNs use Railway references such as `${{postgres.RAILWAY_PRIVATE_DOMAIN}}`, port `5432`, and the configured database name. Passwords are generated as URL-safe hex strings. Service endpoints are configured as follows:

| Variable | Value |
| --- | --- |
| UI `BACKEND_URL`; runtime `DISPATCHER_API_INTERNAL_URL`; MCP `DISPATCHER_API_URL`; gateway `DISPATCHER_CALLBACK_URL` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8080` |
| API `DISPATCHER_GATEWAY_URL` | `http://${{gateway.RAILWAY_PRIVATE_DOMAIN}}:4000` |
| API `DISPATCHER_COLLECTOR_INTERNAL_URL` | `http://${{collector.RAILWAY_PRIVATE_DOMAIN}}:4318/v1/traces` |
| Collector `DISPATCHER_OTLP_TRACES_URL` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8080/api/otlp/v1/traces` |
| Collector `DISPATCHER_OTLP_LOGS_URL` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8080/api/otlp/v1/logs` |
| API `DISPATCHER_TOOL_RESOURCE_URL`; MCP `DISPATCHER_MCP_RESOURCE_URL` | Public HTTPS MCP URL including `/mcp` |
| MCP `DISPATCHER_MCP_ISSUER_URL`; runtime `DISPATCHER_PUBLIC_URL` | Public HTTPS dashboard URL |

MCP has `DISPATCHER_MCP_ALLOW_HTTP=true` only to permit its configured private API connection; the advertised MCP resource and issuer use HTTPS.

The initial `Dispatcher` workspace owner is `tal@biskilled.com` (the authenticated Railway account). Its collector key is scoped to `dispatcher-collector` / `production`; additional apps should create their own keys in the admin UI. Mailbox ownership still has to be verified at sign-in. Matching Google and email identities are deliberately not merged automatically: use email sign-in and then link Google, or explicitly provision membership for the verified Google identity.

### Credentials to supply when ready

Set these in Railway's **API service → Variables**:

- Google: `DISPATCHER_GOOGLE_CLIENT_ID`, `DISPATCHER_GOOGLE_CLIENT_SECRET`. Register `https://agentdispatcher-production.up.railway.app/api/auth/google/callback` as the redirect URI.
- Email login: `DISPATCHER_SMTP_HOST`, `DISPATCHER_SMTP_PORT`, `DISPATCHER_SMTP_SENDER`, `DISPATCHER_SMTP_USER`, `DISPATCHER_SMTP_PASSWORD`, `DISPATCHER_SMTP_STARTTLS`.
- Optional AgentDesk identity validation: `DISPATCHER_AGENTDESK_IDENTITY_URL`, when its trusted endpoint is available.

Set these in **gateway → Variables** when enabling real LLM routing:

- `LLM_PROVIDER_MODEL`, for example the provider-qualified model you choose.
- `LLM_API_KEY`, the corresponding provider credential.

Both provider fields must be configured together. Leaving both blank starts an authenticated gateway with no model routes. YAML configuration sources and provider access are never discovered from other apps automatically; authorize those explicitly through `DISPATCHER_CONFIG_SOURCES` and app-specific credentials.

## Redeployment

The initial UI service retains its GitHub source and waits for CI checks before automatic deployment. The other services were deployed explicitly with `railway up`; no automatic database upgrade or coordinated backend release pipeline is enabled.

Use explicit service selectors. Deploy PostgreSQL first, then run `migrate` successfully before API/worker; deploy UI once API readiness passes. Deploy gateway, collector and MCP after their settings are present. Deploy recovery on demand with a fresh archive name. Database upgrades and migration jobs are operator-controlled; do not indiscriminately redeploy every service after a commit.

```sh
railway link --project ec055b41-12f2-4f02-b5a9-ae3de6d152e5 --environment production
railway up --service migrate --detach
railway deployment list --service migrate --json
# Proceed only after successful migration completion.
railway up --service api --detach
railway up --service worker --detach
railway up --service agentdispatcher --detach
```

For non-interactive CLI configuration, Railway 4.66.1 reads `environment edit` JSON from stdin before command-line configuration flags. Use service IDs in the JSON and pipe it securely, or use the Railway UI. Use `railway variable set KEY --stdin --service SERVICE` for secrets; do not print environment exports into logs. See [Railway CLI environment documentation](https://docs.railway.com/cli/environment).

## Deployment verification — 2026-11-03

Runtime code commits: `cf16e05` (Railway/pgvector startup and credential-safe validation) and `1ef6fea` (dynamic backend DNS). Seven always-on services ran successfully; migration and initial backup jobs exited successfully.

Live Railway checks passed:

- Dashboard HTML/assets and `/health/ready` return 200 over HTTPS; unauthenticated dashboard API and MCP calls return 401.
- PostgreSQL reports `vector` version `0.8.7`; a vector distance query returns the expected zero. Two isolated fixture ledgers retain their exact totals after restarting PostgreSQL.
- The Python SDK submits zero-cost synthetic API attempts and scheduled-job lifecycle events through the public dashboard endpoint. Wrong-tenant and wrong-app writes are rejected; ingestion credentials cannot read human dashboard reports.
- The collector requires its inbound bearer token, forwards into its scoped tenant/app/environment, deduplicates repeated exports and excludes private prompt contents. Three zero-cost synthetic spans produce exactly three attempts.
- The gateway requires authentication and returns no configured model routes while provider credentials are absent. No paid provider API was called.
- The independent worker health command passes. The operator backup writes a private archive and checksum/schema manifest on its separate persistent volume. It is an initial point-in-time backup, not an automatic recurring schedule.
- Runtime configurations contain neither the owner database password nor migration/recovery DSNs. The initial workspace and scoped collector credential are provisioned; Google/SMTP sign-in remains unverified until configured.

[Application and Compose CI](https://github.com/biskilled/agentdispatcher/actions/runs/41691754957) verifies the runtime revision, including 100 backend/SDK/PostgreSQL tests and five MCP checks. [Security CI](https://github.com/biskilled/agentdispatcher/actions/runs/41691754792) passes all seven image variants and dependency gates without High/Critical exceptions. Local unit-only execution passed 38 tests and skipped 62 database tests; the full database evidence comes from CI, not those skips.

Synthetic verification data is clearly labelled and costs zero in the initial workspace. Two separate `Synthetic restart fixture` tenants contain only persistence test data and are not memberships of the initial owner. Other applications are not yet instrumented by this deployment: connect each application through its own SDK key or an authorized gateway/collector route.

## Optional temporary password sign-in

For an operator-requested test account, configure these three variables on **API only**:

- `DISPATCHER_TEST_LOGIN_EMAIL`: an already-provisioned email identity. No user or membership is created by a password login.
- `DISPATCHER_TEST_LOGIN_PASSWORD_HASH`: a salted Argon2id PHC value generated with `.venv/bin/python scripts/password_hash.py`. Store it as a Railway secret; never commit a password or its hash. The implementation uses the existing cryptography package with [OWASP's Argon2id profile](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- `DISPATCHER_TEST_LOGIN_EXPIRES_AT`: an explicit timezone-aware ISO timestamp. Password sign-in disappears and new attempts fail after this time. Sessions issued by this method cannot outlive the cutoff.

All three are empty by default. Clearing all three and redeploying disables new password sign-ins; already-issued sessions retain their normal lifetime, bounded by the original cutoff, and can be revoked through normal logout/operator session revocation. Changing the hash also affects new sign-ins only.

The browser shows a password field only while this method is enabled. Google and email links remain available when configured. Password attempts use the shared PostgreSQL account/IP throttle, CSRF Origin check and HttpOnly session cookie; tenant roles are loaded from current memberships on every request. No credentials are bundled in the React build.

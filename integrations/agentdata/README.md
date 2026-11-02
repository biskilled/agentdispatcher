# AgentData analytics connection

Run migrations before provisioning. The deployment operator supplies
`DISPATCHER_MIGRATION_DATABASE_URL` and a random `DISPATCHER_ANALYTICS_PASSWORD`
of at least 32 characters through the secret store, then runs:

```sh
dispatcher analytics-access --tenant TENANT_UUID
```

The command prints the login role name, never its password. Configure an AgentData
PostgreSQL connection with this role and password, pointing at the Dispatcher
database. Each tenant needs a separate connection credential. Discover the `public.llm_usage` view through AgentData's normal PostgreSQL
discovery. The accompanying `llm_usage.yaml` is a ready Cube model for a separate
Cube deployment; AgentData currently exports Cube YAML and has no general Cube-YAML
import endpoint. Its actual relational adapter has been verified against this view.

Access is bound to PostgreSQL `session_user`, independently of generated SQL filters,
session settings and `SET ROLE`. Both the view and underlying ledger enforce this
binding. The credential cannot read identities, sessions, SDK secrets or change data.
It grants tenant-wide analytics and therefore belongs only in an authorised tenant
analytics connection, not a restricted member's browser. PostgreSQL 15+ is required.

Rerun provisioning with a new password to rotate the credential. To remove access,
including reads from existing pooled connections in subsequent transactions:

```sh
dispatcher analytics-access --tenant TENANT_UUID --revoke
```

Example questions and equivalent SQL (also checked against dashboard results):

```sql
-- How many attempts and input tokens did this workspace use?
SELECT count(*) AS attempts, sum(input_tokens) AS input_tokens FROM llm_usage;
-- What usage cost is known, separated by currency and evidence?
SELECT currency, cost_kind, sum(cost) FROM llm_usage GROUP BY currency, cost_kind;
-- Which providers account for the calls?
SELECT provider, count(*) FROM llm_usage GROUP BY provider;
```

These are request costs, excluding separate subscription fees, refunds and invoice
comparisons. NULL cost means unknown. Group monetary measures by currency and
cost_kind; calculated and app-reported estimates are not provider invoices.
Attempts include retries; distinct operation IDs count logical work. Joining jobs
or invoices must not multiply attempt rows. Reported user IDs are attribution,
while `verified_user_id` identifies server-validated user delegation.


## Observe AgentData's own LLM work

`agentdata.patch` adds the opt-in gateway bridge to AgentData's shared completion
and prompt-loader entry points. It has been applied to the sibling checkout and
verified there. No production bindings, credentials or deployment were changed.
Install `packages/sdk` into the application's environment. Set
`AGENTDATA_DISPATCHER_BINDINGS` to a server-controlled JSON map keyed by the
**authenticated AgentData client ID**, with entries shaped as follows:

```json
{
  "endpoint_env": "DISPATCHER_ENDPOINT",
  "key_env": "TENANT_MONITOR_KEY",
  "app": "AgentData",
  "environment": "production",
  "gateway_endpoint_env": "TENANT_GATEWAY_BASE_URL",
  "gateway_key_env": "TENANT_LLM_KEY"
}
```

The gateway base URL includes `/v1`. Use distinct SDK and LiteLLM credentials,
scoped to the same tenant/app/environment, and permitted model aliases in the
application YAML. Existing budget and egress checks remain in place; the bridge
also checks egress for the selected gateway. No mapping means no tenant fallback:
unmapped calls remain unmonitored and emit a coverage warning. No bindings means
normal application behaviour with no monitoring dependency.

The gateway records billable attempts, including its retries/fallbacks. The SDK
stores a correlated observation, so the same request is not charged twice. Prompt
calls carry their feature key and a SHA-256 digest of the effective loaded prompt
configuration and resolved model/token limit. This digest identifies the effective
prompt configuration; it is not a raw YAML-file digest or proof of deployment.
Neither prompt text nor provider credentials enter Dispatcher telemetry. Direct
shared completions without a prompt-loader context may use a configured
`config_version_env`. Embeddings and other clients outside the shared completion
entry point remain uncovered by this bridge.

## Verification

The harness uses the actual AgentData relational adapter to discover/profile the
view and answer the three questions above with two tenant-bound credentials. It
then exercises the actual patched prompt/completion modules against a local
synthetic gateway and compares canonical charges with SDK references. The real
LiteLLM image/callback is verified separately in Compose CI. Seventeen AgentData
typed-output regression tests also pass. No production AgentData registry is
changed and no paid provider request runs.

```sh
TEST_DATABASE_URL=YOUR_DISPOSABLE_OPERATOR_DSN python integrations/agentdata/verify.py \
  --env-file /path/to/dispatcher.env --agentdata /path/to/agentdata \
  --python /path/to/agentdata/venv/bin/python --applied
```

Without `--applied`, the harness prepares the patch in a temporary module overlay
against an unmodified checkout. Provisioned fixture keys and analytics access are
revoked on exit. Deploying the sibling application and configuring its tenant
bindings remain operator deployment steps.

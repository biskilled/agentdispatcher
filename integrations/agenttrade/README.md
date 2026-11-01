# AgentTrade integration

The optional bridge instruments AgentTrade's shared `meter_provider` once, then
binds trusted organisation scope at its scheduler, analysis, research and
account-refresh entrypoints. Each thread-pool submission copies its own context.
Global portfolio/rescan jobs resolve each organisation before choosing a key.
There is no default cross-tenant credential.

The integration was applied to the real AgentTrade checkout. Its automatic capture
hook recorded commit `38a655e` on the existing local branch; this work did not push
that branch. The nine-file patch is provided for review against source baseline
`56dd39c`. `prepare_patch.py` accepts an explicit clean checkout path and fails if
expected source anchors drift. It does not change that checkout.

Install the AgentDispatcher SDK into the advisor environment (a built SDK wheel
can be used in deployment). Configure `AGENTTRADE_DISPATCHER_BINDINGS` as a JSON map
from trusted AgentTrade organisation IDs to:

```json
{
  "endpoint_env": "MY_DISPATCHER_ENDPOINT",
  "key_env": "MY_TENANT_SDK_KEY",
  "app": "AgentTrade",
  "environment": "production",
  "config_version_env": "DEPLOYED_CONFIG_DIGEST",
  "context": {"project": "AgentTrade"},
  "providers": {
    "anthropic": {"resource_kind": "llm", "api_id": "my-anthropic-plan"},
    "coingecko": {"api_id": "my-market-plan", "connection_id": "my-market-account"}
  }
}
```

These are operator-supplied bindings, not vendor pricing declarations. Create API
plans/connections in Dispatcher and use their IDs. Provider entries are explicit;
providers absent from the map remain uncovered. Secrets live in the referenced
environment variables. Each organisation uses its own tenant/app/environment SDK
key. Rotate by changing the secret and restarting the app; revoke the previous key
in Dispatcher. Set the config digest from the actual deployed YAML, not a proposed
configuration. User IDs are not invented for background jobs.

No bindings means no monitoring dependency on the normal application path. A missing
package or invalid binding logs unavailable coverage. Exporter failures cannot
change provider return values or exceptions. Registry counters expose unmapped
scopes/setup failures; monitor counters expose delivered, failed and dropped exports.
Direct calls outside the shared meter, providers outside the configured map,
unscoped global work, internal library retries and unconsumed streaming bodies remain
outside this adapter's coverage. Do not treat the dashboard as a complete invoice.

Verification: 59 existing/new AgentTrade provider, scheduler and research tests pass.
The synthetic end-to-end harness exercises real scheduler and provider-meter code,
thread-pool calls, HTTP ingestion, PostgreSQL and the dashboard API for two tenants:
each has five attempts, 14 input tokens and USD 0.036 using explicit fixture prices.
It checks timeouts, rejected requests, failed jobs, config attribution and privacy.
Provider responses and the scheduler's business database are mocked; no trade or
paid provider call runs. Run it with explicit local environment/interpreter paths:

```sh
python integrations/agenttrade/verify.py --env-file /path/to/dispatcher.env \
  --agenttrade /path/to/agentTrade --python /path/to/advisor/venv/bin/python
```

The harness creates isolated synthetic Dispatcher tenants and revokes its keys at
the end. Automatic source coverage discovery, MCP steps, durable queue handoff and
SDK/LiteLLM overlap correlation still need their own integration verification.

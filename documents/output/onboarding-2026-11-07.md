# Sources onboarding and bundled account collector — 2026-11-07

Application LLM calls now creates an LLM key with a required connection name and
optional application/environment. An omitted application uses the initial name;
an omitted environment uses `DISPATCHER_GATEWAY_DEFAULT_ENVIRONMENT` (default
`default`). Renaming a connection does not change its established usage scope.

Provider/model multi-select controls use the live LiteLLM route catalog. Refresh
fetches `/v1/models` and sanitized `/model/info` labels through the API; provider
secrets and infrastructure URLs are not returned to the browser. Only selected
route IDs are authorized. Newly configured models appear after refresh without
silently widening permissions. New vendor models must first be enabled in LiteLLM.
The setup panel includes Python and YAML examples using Dispatcher-issued keys.

CLI account usage offers one macOS collector download containing the account reader,
uploader and Python runtime. It does not replace coding tools. `--configure` stores
an owner-only sync key; `--interval` runs periodic collection until stopped. No
startup service is installed. Upstream CodexBar 0.84.0 readers are digest-pinned and
preserved unchanged, with upstream resources/notices and all component licenses.
Windows native collection is not included. Intel code is bundled but runtime tests
used Apple Silicon. This release is ad-hoc signed, not Apple notarized.

Verification: 23 focused backend/collector tests, including a packaged upload with
no Python/CodexBar on PATH; 10 desktop/mobile browser regressions; TypeScript/Vite
build; Ruff and diff checks. Final licensed artifact rechecked with all four collector
tests. Reader binaries were compared with the verified upstream archives. No live
provider requests or account credentials were used. Live rollout results follow.

## Published and deployed

Implementation: `c3528ff28062a44acac7a9dfb42eed6b6803182f`, pushed directly to main
with `[skip ci]`; GitHub Actions remained disabled.

- API deployment: `c2167e25-734c-4959-9675-24407bcfeaa3` — SUCCESS.
- UI deployment: `35eb319e-4ddf-485a-9c94-1f939ad66e50` — SUCCESS.
- Download: https://github.com/biskilled/agentdispatcher/releases/tag/collector-v0.1.0
- ZIP SHA-256: `4690f78ade0a357485a58aa36265e7fc288c12b53f2f8e2b02b122d195673e58`.

The published ZIP was downloaded again, its checksum and executable permissions
verified, and its included reader reported CodexBar 0.84.0. Production verification
passed desktop/mobile Sources and Settings checks, secure password login/logout,
owner scope, unauthorized gateway rejection, and two password browser tests.
The four labeled synthetic events remain excluded from default usage totals.
Live LiteLLM reports `no_models`; provider/model configuration is still needed before
real gateway calls or populated dropdowns. No paid inference or live account reads
were performed. AgentDesk task TA10010 is recorded as review, score 4.

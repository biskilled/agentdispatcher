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

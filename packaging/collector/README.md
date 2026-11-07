# AgentDispatcher account collector

This download includes the account reader (CodexBar), uploader and Python runtime.
It does not replace Codex, Cursor, Claude Code or other coding tools, intercept their
requests, or change their configuration. It reports account limits/balances that the
included reader can access; availability depends on each provider's sign-in and API.
No separate CodexBar, Python or Dispatcher SDK installation is required.

Unzip, open a terminal in this directory, then run:

```sh
./AgentDispatcherCollector --configure
./AgentDispatcherCollector --interval 300
```

Configure with your Dispatcher app URL and a key from Sources → CLI account usage.
The key is saved to an owner-only local file. Set DISPATCHER_COLLECTOR_CONFIG or
pass --config to choose its location. DISPATCHER_URL and DISPATCHER_ACCOUNT_KEY
can override saved values for managed environments. Ctrl-C stops periodic collection;
it does not install an automatic login/startup service. Without --interval it runs once.

Use --provider codex (or another supported provider ID) to select an account reader.
Use --reader --help to inspect the included reader, or --reader --version to show its
version. Additional provider authentication may be required on your device. Existing
CodexBar reader preferences are honored. Provider credentials remain local; only
selected measurement/display fields are sent to Dispatcher. Refreshes never add
request charges. All actual model calls through LiteLLM are monitored separately.

This build supports macOS Apple Silicon and Intel. The native reader does not support
Windows. Linux readers exist upstream but a Linux collector package is not included
in this release. Runtime testing for this release used Apple Silicon; Intel code is
included in the universal binary but was not tested on an Intel machine.

This release is ad-hoc signed, not Apple Developer signed/notarized. macOS may require
explicit approval through Privacy & Security before running a downloaded executable.
Verify the published SHA-256 checksum and provenance before approval.

AgentDispatcher: Apache-2.0, https://github.com/biskilled/agentdispatcher
CodexBar 0.84.0: MIT, Peter Steinberger and contributors,
https://github.com/steipete/CodexBar. Unmodified platform readers/resources are included;
upstream digests and original third-party notices are shipped in this archive.
Python runtime: Python Software Foundation license. PyInstaller's bootloader is
redistributable under its GPL exception. See the included license texts.

## Rebuilding

On macOS, use a universal2 Python runtime (this release used CPython 3.12.10).
Install `packaging/collector/requirements-build.txt` in your build environment,
then run `python scripts/build_collector.py`. Upstream archives are checksum-verified
before extraction. Output is written to `dist/collector` with a SHA-256 sidecar.
`--output` chooses another destination; `--signing-identity` accepts an Apple signing
identity but notarization remains a separate operator step. No GitHub Actions run
is required. Test with `DISPATCHER_TEST_COLLECTOR` set to the built executable and
the repository's normal isolated `TEST_DATABASE_URL` before publishing.

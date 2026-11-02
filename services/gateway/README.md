# Gateway dependency backport

The image starts from the signed LiteLLM base pinned in `.env.example`. Dispatcher
applies compatible OS/dependency updates and an explicit dependency-only fork named
`1.106.6+dispatcher.1`. It preserves the upstream runtime code and original licenses.
This derived image is maintained by Dispatcher, not signed or released by LiteLLM.

`dependency-backport.json` records the exact upstream contract, replacement and
provenance. It follows the Python 3.11+ constraint proposed in
[LiteLLM PR 48802](https://github.com/BerriAI/litellm/pull/48802), which was unmerged
when adopted. Our gateway uses Python 3.13. The fixed filelock version is pinned in
`security-requirements.lock`. The patch fails if the upstream version or constraint
changes, updates the installed version/RECORD hashes, and embeds its provenance in
the distribution metadata. It never ignores a failed dependency check.

Build verification runs `pip check` and checks FileLock/Timeout mutual exclusion and
release across real processes. Compose CI exercises startup, tenant keys, streaming,
callbacks, correlation and routing against synthetic provider responses. Advisory CI
also checks the original upstream LiteLLM version, so the local version cannot hide
an advisory against unchanged upstream code. Image scanning still covers installed
dependencies and OS packages.

Remove the backport when a verified upstream release supports fixed filelock versions.
Update the base, notices and dependency locks together; rerun both functional and
security workflows. Do not loosen the patch's drift checks to accommodate an upgrade.

# Third-party notices

AgentDispatcher's original code is licensed under Apache-2.0. This does not relicense dependencies.

The authoritative generated attribution and verbatim package license texts for the pinned Python runtime and shipped JavaScript dependencies are in [third_party/notices.json](third_party/notices.json). The same artifact is served by the UI's Open-source licenses view. Regenerate it with `python scripts/notices.py` after installing the exact dependency locks. The generator rejects missing license declarations/texts and AGPL/proprietary declarations; this is a basic gate, not an exhaustive legal review or a container SBOM.

Special attention: Psycopg and its binary package retain LGPL-3.0-only terms. They are used as separate, unmodified Python packages, and their bundled upstream notices are preserved in the artifact. Users can replace/rebuild them from the upstream source. Python, Node, PostgreSQL and Nginx base images retain their own included licenses and notices.

Optional services are distributed as upstream images and are not vendored into the application:

| Project | Role | Upstream |
| --- | --- | --- |
| LiteLLM | Optional gateway service; real container callback verified | https://github.com/BerriAI/litellm |
| OpenTelemetry Collector Contrib | Optional authenticated telemetry intake | https://github.com/open-telemetry/opentelemetry-collector-contrib |
| PostgreSQL | Durable tenant data | https://www.postgresql.org/about/licence/ |
| Nginx | Static UI and same-origin proxy | https://nginx.org/en/LICENSE |

The optional MCP service uses the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
under its MIT license. Its isolated pinned dependency closure and original license texts are in
[services/mcp/third_party/notices.json](services/mcp/third_party/notices.json), and are also included
in the UI's combined notice artifact. Run `python scripts/notices.py --python-only-root services/mcp`
using the MCP service environment before regenerating the combined artifact with the main environment.

Pinned upstream component versions, source links and original license texts are in
[third_party/services.json](third_party/services.json), included in the combined UI
credits. Versions are checked against `.env.example`. LiteLLM's community code is
MIT; enterprise directories retain separate terms. AgentDispatcher uses community
key/routing/callback paths, requires no enterprise license and does not relicense
those upstream components. QuotaBar and CodexBar informed planning; their code is
not included.

Development and optional platform package attribution is recorded separately in
[third_party/development.json](third_party/development.json), using the locked npm
inventory and Python development closure. These build tools are not bundled into
the React application. Run `python scripts/notices.py --development` after updates.
The gate rejects missing/unknown, AGPL, BUSL, SSPL and commercial/proprietary license
declarations. This is an automated policy check, not a substitute for reviewing
new dependency terms.

The Release security evidence workflow produces SPDX inventories and vulnerability
reports for every deployed image (API/worker, UI, MCP, recovery, PostgreSQL,
LiteLLM and collector). Upstream operating-system packages retain the license texts
and source provisions supplied in their images. CI archives inventories with the
commit and verifies LiteLLM's signature against its pinned upstream signing key.
See `documents/output/release-verification.md` for the evidence and release limits.

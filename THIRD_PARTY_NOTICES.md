# Third-party notices

AgentDispatcher's original code is licensed under Apache-2.0. This does not relicense dependencies.

The authoritative generated attribution and verbatim package license texts for the pinned Python runtime and shipped JavaScript dependencies are in [third_party/notices.json](third_party/notices.json). The same artifact is served by the UI's Open-source licenses view. Regenerate it with `python scripts/notices.py` after installing the exact dependency locks. The generator rejects missing license declarations/texts and AGPL/proprietary declarations; this is a basic gate, not an exhaustive legal review or a container SBOM.

Special attention: Psycopg and its binary package retain LGPL-3.0-only terms. They are used as separate, unmodified Python packages, and their bundled upstream notices are preserved in the artifact. Users can replace/rebuild them from the upstream source. Python, Node, PostgreSQL and Nginx base images retain their own included licenses and notices.

Optional services are distributed as upstream images and are not vendored into the application:

| Project | Role | Upstream |
| --- | --- | --- |
| LiteLLM | Optional gateway service; selected release needs container verification | https://github.com/BerriAI/litellm |
| OpenTelemetry Collector Contrib | Optional internal telemetry diagnostics | https://github.com/open-telemetry/opentelemetry-collector-contrib |
| PostgreSQL | Durable tenant data | https://www.postgresql.org/about/licence/ |
| Nginx | Static UI and same-origin proxy | https://nginx.org/en/LICENSE |

LiteLLM's enterprise components have separate terms. The starter configuration does not request enterprise features; inspecting the selected image's complete contents and notices is a release requirement still tracked under TA10007. Container/OS dependency inventory, dev-tool notices and a full distribution audit remain pending. QuotaBar and CodexBar informed earlier planning; their code is not included.

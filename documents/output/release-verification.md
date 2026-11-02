# Release verification — 2026-11-02

**Release blocked.** Application acceptance fixtures pass, but live authentication
acceptance and two upstream container findings remain open. The security workflow
fails on High/Critical findings, including unfixed ones. No advisory exceptions,
blanket ignores or changed severity thresholds have been added.

## Reproducible evidence

- [Functional CI 41378379070](https://github.com/biskilled/agentdispatcher/actions/runs/41378379070)
  passed application/MCP tests, clean Compose/demo, independent database/API/UI/worker
  restarts, persistence, optional backup, real LiteLLM streaming/key/correlation checks
  and authenticated collector trace/log ingestion.
- [Security CI 41378952571](https://github.com/biskilled/agentdispatcher/actions/runs/41378952571)
  built/scanned all seven image variants at `22507f2`, passed the Python/npm advisory
  job and verified the upstream LiteLLM signature. API/worker, UI, MCP, PostgreSQL
  and recovery scans have no High/Critical matches. Gateway and collector each
  retain one High match. [Compact results](release-security-summary.json) preserve
  the package versions and advisory IDs; complete inventories/reports are workflow
  artifacts with 30-day retention. Download them before publishing a release.
- Local PostgreSQL tests cover fresh-database backup/restore, revoked copied
  credentials, tenant deletion/retention, exports, forced RLS and pooled scopes.
  Desktop/mobile dashboard and connected-YAML browser suites pass. Actual AgentTrade
  and AgentData integrations use synthetic provider responses and isolated tenants.
  This does not verify paid-provider invoices or production app deployment.

## Changes made after scanning

The Python service base moved to supported Python 3.12.16 on Alpine 3.24; service
images apply available OS updates. Recovery uses the PostgreSQL 17 client. The UI
image also applies available Alpine updates. These changes removed the initial
High/Critical OS findings and passed clean installation/recovery fixtures.

The gateway derives from LiteLLM 1.106.6. CI verifies its upstream base signature
before building; the derived image is not claimed to be upstream-signed. Its small
security lock updates pyasn1, ddtrace and its internal dependency, dnspython and
pypdf, and applies available Wolfi updates. `pip check` must pass. The updated image
was built and scanned successfully; its remaining finding is listed below.

SBOM generation uses Syft JSON with Go symbol capture. This preserves evidence used
by Grype to exclude unreachable standard-library matches; converting to SPDX had
discarded that evidence for the PostgreSQL helper binary. This is scanner-supported
matching, not a vulnerability waiver. See [Anchore's Go scanning guidance](https://oss.anchore.com/docs/capabilities/go/).

## Remaining security acceptance

| Image | Finding | Why still open | Completion condition |
| --- | --- | --- | --- |
| LiteLLM 1.106.6 derivative | filelock 3.32.7, GHSA-v4x8-3wr5-3wq8 | Published fix 4.2.1 conflicts with LiteLLM's declared `filelock<4` dependency. Installing it caused `pip check` to fail. An older compatible candidate, 3.20.3, also has advisories. | Use a compatible, verified fixed upstream dependency set or a maintained reviewed backport, then rerun gateway acceptance and image scans. |
| Collector Contrib 0.164.0 | go-jose/v4 4.1.5, GHSA-mgcc-cww5-fp2q | The distributed binary embeds the affected module; its fix is 4.1.6. | Use a verified collector image containing the fix, or a separately reviewed minimal distribution, then rerun trace/log/authentication and image scans. |

The [filelock advisory](https://github.com/tox-dev/filelock/security/advisories/GHSA-v4x8-3wr5-3wq8)
concerns SQLite-backed read/write locks with attacker-controlled filesystem entries.
The [go-jose advisory](https://github.com/go-jose/go-jose/security/advisories/GHSA-mgcc-cww5-fp2q)
concerns excessive CPU when parsing crafted RSA JWKs. The shipped collector uses
literal bearer-token authentication, not JWK/OIDC authentication; that reduces the
apparent exposed path but is not proof that every upstream path is unreachable.
Neither finding is suppressed or claimed fixed.

The core demo does not start these optional gateway/telemetry profiles. They remain
development-preview integrations pending release clearance.

## Authentication acceptance

Google OIDC, email-link sessions, invitation/membership boundaries, scoped hashed
SDK keys and AgentDesk attribution have automated positive/negative tests. Live
Google sign-in and email delivery require deployment credentials and a human login.
No such credentials were provided. The connected AgentDesk host returned HTTP 404
for `/auth/dispatcher-identity` during this verification.

The [AgentDesk identity patch and verification instructions](../../integrations/agentdesk/README.md)
are prepared and applied to the sibling checkout. Deploy that endpoint, configure
the documented identity URL and Google/SMTP settings, then verify owner/member
sign-in, tenant switching and revocation on desktop/mobile. Supply configuration
through an environment/secret file, never by placing credentials in Git or chat.
CLI integration keys are deliberately not accepted as human identity credentials.

## Attribution and scope

Runtime/component credits include upstream source links and license texts;
development/platform attribution is separate. CI rejects prohibited or missing
license declarations and explicit enterprise imports/callbacks/license activation
references in owned source/configuration. This static check does not establish the
license of every dormant file inside upstream images; those retain their upstream
notices and separate terms. No enterprise license is required by the tested paths.
See [third-party notices](../../THIRD_PARTY_NOTICES.md).

All durable application data is PostgreSQL-backed and tenant-scoped. Default
telemetry excludes prompt/response content and credentials. Provider terms and
external-account permissions remain configuration inputs; uninstrumented calls,
missing exporter delivery and unknown prices must remain visible coverage gaps.

# Release verification — 2026-11-02

**Both blocking findings resolved.** Functional CI and the release-security workflow
pass for the derived gateway and minimal collector. Live authentication setup is
deferred by the owner. The security workflow still fails on High/Critical findings,
including unfixed ones. No advisory exceptions, blanket ignores or changed severity
thresholds have been added. Lower-severity findings remain visible in the reports;
a passing release gate does not mean every dependency is vulnerability-free.

## Reproducible evidence

- [Functional CI 41504199675](https://github.com/biskilled/agentdispatcher/actions/runs/41504199675)
  passed 96 application tests, five MCP checks, clean Compose/demo, independent database/API/UI/worker
  restarts, persistence, optional backup, real LiteLLM streaming/key/correlation checks
  and authenticated collector trace/log ingestion.
- [Security CI 41504199537](https://github.com/biskilled/agentdispatcher/actions/runs/41504199537)
  built/scanned all seven image variants at `ea82115`, passed the Python/npm advisory
  job and verified the upstream LiteLLM signature. All seven images have no
  High/Critical matches. The collector has no matches at any severity in this scan.
  [Compact results](release-security-summary.json) preserve per-image severity counts;
  complete inventories/reports and collector dependency/license evidence are workflow
  artifacts with 30-day retention. Download them before publishing a release.
  Collector license-policy checks pass and its built Go dependency files exactly
  match the committed locks.
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
security lock updates pyasn1, ddtrace and its internal dependency, dnspython, pypdf
and filelock, and applies available Wolfi updates. The explicit dependency-only fork
`1.106.6+dispatcher.1` supports filelock 4.2.4 on Python 3.13, following the Python
3.11+ constraint in [unmerged upstream PR 48802](https://github.com/BerriAI/litellm/pull/48802).
Original runtime code and licenses are preserved. `pip check` and a cross-process
FileLock/Timeout test must pass. The patch rejects upstream version/constraint drift
and records its provenance and changed metadata checksums. Upstream LiteLLM is also
audited under its original version so the local label cannot conceal advisories.
See [gateway maintenance/removal instructions](../../services/gateway/README.md).

The collector is built with official OCB and only the components needed for our
trace/log pipeline. The compiled binary no longer contains go-jose; the broader
module graph additionally pins fixed go-jose/v4 4.1.6. The build has checked-in Go
module/checksum locks and includes dependency license texts and binary module evidence.
See [collector build instructions](../../services/collector/README.md).

SBOM generation uses Syft JSON with Go symbol capture. This preserves evidence used
by Grype to exclude unreachable standard-library matches; converting to SPDX had
discarded that evidence for the PostgreSQL helper binary. This is scanner-supported
matching, not a vulnerability waiver. See [Anchore's Go scanning guidance](https://oss.anchore.com/docs/capabilities/go/).

## Resolved security findings

| Image | Original finding | Verified resolution |
| --- | --- | --- |
| LiteLLM derivative | filelock 3.32.7, GHSA-v4x8-3wr5-3wq8 | Installed filelock 4.2.4; explicit local dependency backport; dependency/locking tests, real gateway fixtures and image scan pass. |
| Minimal collector | go-jose/v4 4.1.5, GHSA-mgcc-cww5-fp2q | Vulnerable module absent from compiled binary; broader graph replaces it with 4.1.6; authenticated ingestion and image scan pass. |

The [filelock advisory](https://github.com/tox-dev/filelock/security/advisories/GHSA-v4x8-3wr5-3wq8)
concerns SQLite-backed read/write locks with attacker-controlled filesystem entries.
The [go-jose advisory](https://github.com/go-jose/go-jose/security/advisories/GHSA-mgcc-cww5-fp2q)
concerns excessive CPU when parsing crafted RSA JWKs. Both are resolved through
package/build changes, rather than a reachability waiver.

The core demo does not start these optional gateway/telemetry profiles. Deployment
still requires environment-specific credentials, network configuration and live checks.

## Deferred authentication deployment setup

On 2026-11-02 the owner confirmed that credentials will be configured later in Railway
or locally and are not required for implementation completion. TA10003 is ready for
review based on the implemented environment variables and automated verification.
The following live checks remain deployment steps, not current implementation blockers.

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

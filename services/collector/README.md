# Minimal collector distribution

The optional telemetry image builds a small collector using the official OpenTelemetry
Collector Builder. `builder.yaml` lists only the OTLP receiver, HTTP exporter, batch
processor, bearer-token authentication, health check and file/environment configuration
providers required by `config.yaml`. Shared dependencies still include JOSE in the
module graph; the manifest explicitly replaces it with fixed go-jose/v4 4.1.6.
The image scan checks the resulting binary without advisory suppressions.

The component versions follow the upstream 0.164.0 distribution manifest (including
Contrib extension patch 0.164.1). The binary is labelled `0.164.0-dispatcher.1`; it
replaces the stock binary in the pinned upstream base, retaining its certificates,
non-root identity and notices. The Go compiler/builder/license-tool versions are
configured in `.env.example`. Existing local environments must add these variables
before rebuilding the telemetry profile.

The checked-in `go.mod` and `go.sum` pin the resolved dependency closure. Normal builds
generate component source, then build using those locks without resolving upgrades.
To update them, run the pinned OCB with `builder.yaml` in the configured Go build
environment, review the resulting module/checksum changes, and rerun both CI workflows.

The image includes compiled dependency license texts, module inventory and Go module
checksums under `/licenses/dispatcher`. CI archives these with the image inventory and
scan results. Compiled binary module versions are retained separately from the full
module graph. Changing components
requires reviewing the module graph/licenses and rerunning authenticated trace/log
ingestion and the complete image scan.

Build with `docker compose --profile telemetry build collector`. No host Go install is
required. The first build downloads Go modules; the running collector needs no build
tools. Published dependency findings remain blocking; no VEX exceptions are applied.

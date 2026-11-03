ARG GO_IMAGE
ARG OTEL_IMAGE
FROM ${GO_IMAGE} AS build
ARG COLLECTOR_BUILDER_VERSION
ARG GO_LICENSES_VERSION
WORKDIR /build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
COPY services/collector/builder.yaml ./builder.yaml
RUN go install go.opentelemetry.io/collector/cmd/builder@${COLLECTOR_BUILDER_VERSION} \
    && builder --skip-get-modules --skip-compilation --config builder.yaml
COPY services/collector/go.mod services/collector/go.sum /build/collector/
RUN GOFLAGS=-mod=readonly builder --skip-generate --skip-get-modules --config builder.yaml
WORKDIR /build/collector
COPY LICENSE ./LICENSE
# Ship the compiled dependency licenses, not only the collector's top-level notice.
RUN go run github.com/google/go-licenses/v2@${GO_LICENSES_VERSION} check ./... --disallowed_types=forbidden,restricted,unknown \
    && go run github.com/google/go-licenses/v2@${GO_LICENSES_VERSION} save ./... --save_path=/licenses \
    && go run github.com/google/go-licenses/v2@${GO_LICENSES_VERSION} report ./... > /licenses/licenses.csv \
    && cp /usr/local/go/LICENSE /licenses/GO-LICENSE \
    && go list -m all > /licenses/modules.txt \
    && go version -m ./otelcol-contrib > /licenses/binary-modules.txt
FROM ${OTEL_IMAGE}
COPY services/collector/config.yaml /etc/otelcol-contrib/config.yaml
COPY --from=build /build/collector/otelcol-contrib /otelcol-contrib
COPY --from=build /licenses /licenses/dispatcher
COPY --from=build /build/collector/go.mod /build/collector/go.sum /licenses/dispatcher/

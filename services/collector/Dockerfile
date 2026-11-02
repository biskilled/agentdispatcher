ARG GO_IMAGE
ARG OTEL_IMAGE
FROM ${GO_IMAGE} AS build
ARG COLLECTOR_BUILDER_VERSION
ARG GO_LICENSES_VERSION
WORKDIR /build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
COPY services/collector/builder.yaml ./builder.yaml
RUN go install go.opentelemetry.io/collector/cmd/builder@${COLLECTOR_BUILDER_VERSION} \
    && builder --config builder.yaml
WORKDIR /build/collector
COPY LICENSE ./LICENSE
# Ship the compiled dependency licenses, not only the collector's top-level notice.
RUN go run github.com/google/go-licenses/v2@${GO_LICENSES_VERSION} save ./... --save_path=/licenses \
    && cp /usr/local/go/LICENSE /licenses/GO-LICENSE \
    && go list -m all > /licenses/modules.txt \
    && if grep -q 'github.com/go-jose/go-jose' /licenses/modules.txt; then exit 1; fi
FROM ${OTEL_IMAGE}
COPY --from=build /build/collector/otelcol-contrib /otelcol-contrib
COPY --from=build /licenses /licenses/dispatcher
COPY --from=build /build/collector/go.mod /build/collector/go.sum /licenses/dispatcher/

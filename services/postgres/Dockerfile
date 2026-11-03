ARG POSTGRES_IMAGE
FROM ${POSTGRES_IMAGE} AS build
ARG PGVECTOR_SOURCE_URL
ARG PGVECTOR_SHA256
USER root
RUN apk add --no-cache build-base
ADD ${PGVECTOR_SOURCE_URL} /tmp/pgvector.tar.gz
RUN echo "${PGVECTOR_SHA256}  /tmp/pgvector.tar.gz" | sha256sum -c - \
    && mkdir /tmp/pgvector \
    && tar xzf /tmp/pgvector.tar.gz --strip-components=1 -C /tmp/pgvector \
    && make -C /tmp/pgvector OPTFLAGS="" with_llvm=no \
    && make -C /tmp/pgvector with_llvm=no install
FROM ${POSTGRES_IMAGE}
COPY --from=build /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/vector.so
COPY --from=build /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/
COPY --from=build /tmp/pgvector/LICENSE /tmp/pgvector/README.md /usr/local/share/doc/pgvector/
COPY services/postgres/init-vector.sql /docker-entrypoint-initdb.d/10-vector.sql

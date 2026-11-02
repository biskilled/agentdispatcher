ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
ARG INSTALL_GIT=false
ARG INSTALL_POSTGRES_CLIENT=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN set -eu; apk upgrade --no-cache; package_list=""; \
    if [ "$INSTALL_GIT" = "true" ]; then package_list="$package_list git openssh-client"; fi; \
    if [ "$INSTALL_POSTGRES_CLIENT" = "true" ]; then package_list="$package_list postgresql17-client"; fi; \
    if [ -n "$package_list" ]; then apk add --no-cache $package_list; fi
COPY requirements.lock pyproject.toml LICENSE ./
COPY packages ./packages
COPY scripts ./scripts
COPY third_party ./third_party
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps . \
    && adduser -D dispatcher
USER dispatcher
CMD ["uvicorn", "dispatcher.api:create_app", "--factory"]

ARG PYTHON_IMAGE=python:3.12.12-slim
FROM ${PYTHON_IMAGE}
ARG INSTALL_GIT=false
ARG INSTALL_POSTGRES_CLIENT=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN package_list=""; \
    if [ "$INSTALL_GIT" = "true" ]; then package_list="$package_list git openssh-client"; fi; \
    if [ "$INSTALL_POSTGRES_CLIENT" = "true" ]; then package_list="$package_list postgresql-client"; fi; \
    if [ -n "$package_list" ]; then apt-get update \
      && apt-get install -y --no-install-recommends $package_list \
      && rm -rf /var/lib/apt/lists/*; fi
COPY requirements.lock pyproject.toml LICENSE ./
COPY packages ./packages
COPY scripts ./scripts
COPY third_party ./third_party
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps . \
    && useradd --create-home dispatcher
USER dispatcher
CMD ["uvicorn", "dispatcher.api:create_app", "--factory"]

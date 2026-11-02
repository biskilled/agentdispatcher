ARG PYTHON_IMAGE=python:3.12.12-slim
FROM ${PYTHON_IMAGE}
ARG INSTALL_GIT=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN if [ "$INSTALL_GIT" = "true" ]; then apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*; fi
COPY requirements.lock pyproject.toml LICENSE ./
COPY packages ./packages
COPY scripts ./scripts
COPY third_party ./third_party
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps . \
    && useradd --create-home dispatcher
USER dispatcher
CMD ["uvicorn", "dispatcher.api:create_app", "--factory"]

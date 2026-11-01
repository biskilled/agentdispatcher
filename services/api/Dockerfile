ARG PYTHON_IMAGE=python:3.12.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock pyproject.toml LICENSE ./
COPY packages ./packages
COPY scripts ./scripts
COPY third_party ./third_party
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-deps . \
    && useradd --create-home dispatcher
USER dispatcher
CMD ["uvicorn", "dispatcher.api:create_app", "--factory"]

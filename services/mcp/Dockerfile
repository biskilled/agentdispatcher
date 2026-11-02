ARG PYTHON_IMAGE=python:3.12.12-slim
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/mcp/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home dispatcher
COPY services/mcp/server.py ./server.py
COPY services/mcp/third_party ./third_party
COPY LICENSE ./LICENSE
USER dispatcher
CMD ["python", "server.py"]

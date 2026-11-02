ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/mcp/requirements.lock ./requirements.lock
RUN apk upgrade --no-cache && pip install --no-cache-dir -r requirements.lock && adduser -D dispatcher
COPY packages/sdk ./sdk
RUN pip install --no-cache-dir --no-deps ./sdk
COPY services/mcp/server.py services/mcp/proxy.py ./
COPY services/mcp/third_party ./third_party
COPY LICENSE ./LICENSE
USER dispatcher
CMD ["python", "server.py"]

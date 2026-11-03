ARG LITELLM_IMAGE
FROM ${LITELLM_IMAGE}
USER root
COPY services/gateway/config.yaml services/gateway/dispatcher_callbacks.py services/gateway/start.py /app/
# Preserve the upstream application while applying published OS and dependency fixes.
COPY services/gateway/security-requirements.lock /tmp/dispatcher-security.lock
COPY services/gateway/apply_dependency_backport.py services/gateway/dependency-backport.json services/gateway/verify_filelock.py /tmp/
RUN apk upgrade --no-cache \
    && python -m ensurepip \
    && python /tmp/apply_dependency_backport.py /tmp/dependency-backport.json \
    && python -m pip install --no-cache-dir --no-deps -r /tmp/dispatcher-security.lock \
    && python -m pip check \
    && python /tmp/verify_filelock.py

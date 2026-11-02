ARG LITELLM_IMAGE
FROM ${LITELLM_IMAGE}
USER root
# Preserve the upstream application while applying published OS and dependency fixes.
COPY services/gateway/security-requirements.lock /tmp/dispatcher-security.lock
RUN apk upgrade --no-cache \
    && python -m ensurepip \
    && python -m pip install --no-cache-dir --no-deps -r /tmp/dispatcher-security.lock \
    && python -m pip check

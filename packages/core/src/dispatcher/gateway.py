"""LiteLLM virtual-key lifecycle and authenticated, metadata-only callback boundary."""

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException

from dispatcher.auth import require_admin, verifier
from dispatcher.contracts import Principal
from dispatcher.policies import Policies

_SQL_KEY = """
INSERT INTO mng_sdk_keys(id,tenant_id,token_hash,name,app,environment,created_by,expires_at,
purpose,allowed_models) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'gateway',%s)
"""
_SQL_LOOKUP = """
UPDATE mng_sdk_keys SET last_used_at=now() WHERE id=%s AND purpose='gateway'
AND revoked_at IS NULL AND expires_at>now()
RETURNING id,tenant_id,app,environment,expires_at,allowed_models
"""
_SQL_KEYS = """
SELECT id,name,app,environment,created_at,expires_at,revoked_at,last_used_at,allowed_models
FROM mng_sdk_keys WHERE tenant_id=%s AND purpose='gateway' ORDER BY created_at DESC
"""
_SQL_AUDIT = """
INSERT INTO mng_auth_audit(tenant_id,actor_id,action,target_id) VALUES(%s,%s,%s,%s)
"""
_SQL_MANAGE = """
SELECT id,token_hash,allowed_models FROM mng_sdk_keys
WHERE id=%s AND tenant_id=%s AND purpose='gateway'
AND revoked_at IS NULL AND expires_at>now() FOR UPDATE
"""


class Gateway:
    """A virtual key can invoke allowed models but is never an SDK or dashboard credential."""

    def __init__(self, db, transport=None):
        self.db, self.settings, self.transport = db, db.settings, transport

    def verify_callback(self, secret: str):
        """Require a separate gateway-to-Dispatcher secret; disabled integrations fail closed."""
        expected = self.settings.gateway_callback_secret.get_secret_value()
        if not expected or not secrets.compare_digest(expected, secret):
            raise HTTPException(401, "Invalid gateway callback credential")

    def principal(self, service_id: UUID, model: str | None = None):
        """Recheck revocation/scope before each provider call and each exported observation."""
        with self.db.auth() as connection:
            row = connection.execute(_SQL_LOOKUP, (service_id,)).fetchone()
        if not row:
            raise HTTPException(401, "Gateway key is expired, revoked or unregistered")
        if model is not None and model not in row["allowed_models"]:
            raise HTTPException(403, "Model is not allowed by this virtual key")
        return Principal(
            tenant_id=row["tenant_id"],
            subject_id=row["id"],
            role="service",
            app=row["app"],
            environment=row["environment"],
            expires_at=row["expires_at"],
            purpose="gateway",
        )

    def keys(self, principal):
        """List tenant gateway metadata, never virtual key secrets or stored hashes."""
        require_admin(principal)
        with self.db.auth() as connection:
            return connection.execute(_SQL_KEYS, (principal.tenant_id,)).fetchall()

    def client(self):
        """Use LiteLLM's management API without exposing the operator credential to clients."""
        if not self.settings.gateway_url or not self.settings.gateway_master_key.get_secret_value():
            raise HTTPException(503, "LiteLLM gateway is not configured")
        return httpx.Client(
            base_url=self.settings.gateway_url.rstrip("/") + "/",
            headers={
                "Authorization": "Bearer " + self.settings.gateway_master_key.get_secret_value()
            },
            timeout=self.settings.http_timeout,
            transport=self.transport,
        )

    def connection(self, principal):
        """Read native model aliases without invoking a provider or exposing provider settings."""
        require_admin(principal)
        result = {
            "base_url": self.settings.gateway_client_url
            or self.settings.public_url.rstrip("/") + "/llm/v1",
            "state": "not_configured",
            "models": [],
        }
        if not self.settings.gateway_url or not self.settings.gateway_master_key.get_secret_value():
            return result
        try:
            with self.client() as client:
                response = client.get("v1/models")
                response.raise_for_status()
                rows = response.json()["data"]
                if not isinstance(rows, list):
                    raise ValueError("Invalid model list")
                models = sorted({row["id"] for row in rows if isinstance(row["id"], str)})
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            # Upstream errors can contain infrastructure details; keep them out of the browser.
            return {**result, "state": "unavailable"}
        return {**result, "state": "ready" if models else "no_models", "models": models}

    def route(self, principal, requested_model, task_id, default_model=None):
        """Select policy routes only when every candidate is also allowed by this virtual key."""
        selected = requested_model
        try:
            self.principal(principal.subject_id, selected)
        except HTTPException as error:
            if error.status_code != 403 or not default_model:
                raise
            selected = default_model
            self.principal(principal.subject_id, selected)
        route = Policies(self.db).route(principal, selected, task_id)
        for model in [route["model"], *route["fallbacks"]]:
            self.principal(principal.subject_id, model)
        return {**route, "requested_model": requested_model}

    def routing(self, principal, service_id, update=None):
        """Manage native LiteLLM aliases/defaults, locking tenant scope against concurrent edits."""
        require_admin(principal)
        with self.db.auth() as connection:
            row = connection.execute(_SQL_MANAGE, (service_id, principal.tenant_id)).fetchone()
            if not row:
                raise HTTPException(404, "Active gateway connection not found")
            try:
                with self.client() as client:
                    response = client.get("key/info", params={"key": row["token_hash"]})
                    response.raise_for_status()
                    info = response.json()["info"]
                    current = self._routing_view(info, row["allowed_models"])
                    if update is None:
                        return current
                    if update.revision != current["revision"]:
                        raise HTTPException(409, "Routing changed. Close and reopen before saving.")
                    self._validate_routing(update, row["allowed_models"])
                    metadata = {
                        **(info.get("metadata") or {}),
                        "dispatcher_service_id": str(service_id),
                        "dispatcher_default_model": update.default_model,
                    }
                    response = client.post(
                        "key/update",
                        json={
                            "key": row["token_hash"],
                            "aliases": update.aliases,
                            "metadata": metadata,
                            # Unknown names must reach our mandatory authorization callback.
                            # The local allow-list still constrains every resolved model.
                            "models": ["*"] if update.default_model else row["allowed_models"],
                        },
                    )
                    response.raise_for_status()
                    connection.execute(
                        _SQL_AUDIT,
                        (
                            principal.tenant_id,
                            principal.subject_id,
                            "gateway_routing.updated",
                            service_id,
                        ),
                    )
                    return self._routing_view(
                        {"aliases": update.aliases, "metadata": metadata}, row["allowed_models"]
                    )
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise HTTPException(502, "LiteLLM routing could not be read or saved") from None

    @staticmethod
    def _routing_view(info, models):
        value = {
            "aliases": info.get("aliases") or {},
            "default_model": (info.get("metadata") or {}).get("dispatcher_default_model"),
            "allowed_models": models,
        }
        revision = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        return {**value, "revision": revision}

    @staticmethod
    def _validate_routing(update, models):
        targets = [*update.aliases.values()]
        if update.default_model:
            targets.append(update.default_model)
        if any(target not in models for target in targets):
            raise HTTPException(
                400, "Services and default must target this connection's allowed models"
            )
        if any(name in models or name == "*" for name in update.aliases):
            raise HTTPException(400, "Service names cannot replace allowed model names or use '*'")

    def issue(self, principal, name, app, environment, models):
        """Create an upstream virtual key then register its scope; unregistered keys cannot run."""
        require_admin(principal)
        service_id = uuid4()
        requested_key = "sk-" + secrets.token_urlsafe(32)
        expiry = datetime.now(UTC) + timedelta(seconds=self.settings.key_seconds)
        with self.client() as client:
            try:
                response = client.post(
                    "key/generate",
                    json={
                        "key": requested_key,
                        "models": models,
                        "key_alias": str(service_id),
                        "duration": f"{self.settings.key_seconds}s",
                        "metadata": {"dispatcher_service_id": str(service_id)},
                    },
                )
                response.raise_for_status()
                secret = response.json()["key"]
                if not isinstance(secret, str) or not secrets.compare_digest(secret, requested_key):
                    raise ValueError("Missing virtual key")
            except (httpx.HTTPError, ValueError, KeyError):
                raise HTTPException(502, "LiteLLM could not create a virtual key") from None
            try:
                with self.db.auth() as connection:
                    connection.execute(
                        _SQL_KEY,
                        (
                            service_id,
                            principal.tenant_id,
                            verifier(secret),
                            name,
                            app,
                            environment,
                            principal.subject_id,
                            expiry,
                            models,
                        ),
                    )
                    connection.execute(
                        _SQL_AUDIT,
                        (
                            principal.tenant_id,
                            principal.subject_id,
                            "gateway_key.created",
                            service_id,
                        ),
                    )
            except Exception:
                try:
                    client.post("key/delete", json={"keys": [secret]}).raise_for_status()
                except httpx.HTTPError:
                    logging.error(
                        "Gateway key registration cleanup failed; unregistered key remains denied"
                    )
                raise
        return {"id": service_id, "secret": secret, "expires_at": expiry, "allowed_models": models}

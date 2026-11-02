"""Poll authorised sources and compare them with app-reported loaded versions."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from pydantic import AwareDatetime, Field

from dispatcher.auth import require_admin
from dispatcher.contracts import Contract

_SQL_LOCK = "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS acquired"
_SQL_HEAD = "SELECT * FROM mem_config_heads WHERE tenant_id=%s AND source_id=%s"
_SQL_HEAD_SAVE = """
INSERT INTO mem_config_heads(tenant_id,source_id,source_contract,digest,revision,
checked_at,error_code)
VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,source_id) DO UPDATE SET
source_contract=EXCLUDED.source_contract,digest=EXCLUDED.digest,revision=EXCLUDED.revision,
checked_at=EXCLUDED.checked_at,error_code=EXCLUDED.error_code
"""
_SQL_RUNTIME_ADD = """
INSERT INTO mem_config_runtime(tenant_id,event_id,source_id,instance_id,digest,success,
occurred_at,service_id,source_contract) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT DO NOTHING RETURNING event_id
"""
_SQL_RUNTIME_ONE = "SELECT * FROM mem_config_runtime WHERE tenant_id=%s AND event_id=%s"
_SQL_RUNTIME = """
SELECT DISTINCT ON(instance_id) instance_id,digest,success,occurred_at,received_at
FROM mem_config_runtime WHERE tenant_id=%s AND source_id=%s AND source_contract=%s
ORDER BY instance_id,occurred_at DESC,received_at DESC LIMIT %s
"""


class RuntimeVersion(Contract):
    """A process reports the hash of loaded bytes, never YAML or provider secrets."""

    event_id: UUID
    instance_id: str = Field(min_length=1, max_length=100)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    success: bool
    occurred_at: AwareDatetime


def save_head(connection, source_id, source, snapshot, at, error=None):
    """Store the last attempted scan; an unavailable source cannot claim current parity."""
    connection.execute(
        _SQL_HEAD_SAVE,
        (
            source.tenant_id,
            source_id,
            source.fingerprint(),
            snapshot.digest if snapshot else None,
            snapshot.revision if snapshot else None,
            at,
            error,
        ),
    )


class ConfigurationMonitor:
    """Reuse connectors and PostgreSQL locks; no additional scheduler or persistent file store."""

    def __init__(self, configurations):
        self.configurations, self.db = configurations, configurations.db

    def poll(self, at=None):
        """Serialize each source across workers and retain safe failures without logging content."""
        at = at or datetime.now(UTC)
        checked = 0
        for source_id, source in self.db.settings.config_sources.items():
            with self.db.tenant(source.tenant_id) as connection:
                acquired = connection.execute(
                    _SQL_LOCK, (f"{source.tenant_id}:config-poll:{source_id}",)
                ).fetchone()["acquired"]
                if not acquired:
                    continue
                head = connection.execute(_SQL_HEAD, (source.tenant_id, source_id)).fetchone()
                if (
                    head
                    and head["source_contract"] == source.fingerprint()
                    and (at - head["checked_at"]).total_seconds()
                    < self.db.settings.config_poll_seconds
                ):
                    continue
                try:
                    # A savepoint keeps a failed scan from poisoning the error-status write.
                    with connection.transaction():
                        self.configurations.scan_source(connection, source_id, source, at)
                except Exception:
                    save_head(connection, source_id, source, None, at, "scan_failed")
                    logging.error("Configuration scan failed; source status records the failure")
                checked += 1
        return checked

    def runtime(self, principal, source_id, event):
        """Only the source's authenticated application may attest to its loaded version."""
        source = self.db.settings.config_sources.get(source_id)
        if (
            principal.role != "service"
            or principal.purpose != "ingest"
            or not source
            or (source.tenant_id, source.app, source.environment)
            != (principal.tenant_id, principal.app, principal.environment)
        ):
            raise HTTPException(404, "Configuration source not found")
        if event.occurred_at > datetime.now(UTC) + timedelta(
            seconds=self.db.settings.config_clock_skew_seconds
        ):
            raise HTTPException(422, "Runtime observation is in the future")
        expected = {
            **event.model_dump(),
            "source_id": source_id,
            "service_id": principal.subject_id,
            "source_contract": source.fingerprint(),
        }
        with self.db.tenant(principal.tenant_id) as connection:
            added = connection.execute(
                _SQL_RUNTIME_ADD,
                (
                    principal.tenant_id,
                    event.event_id,
                    source_id,
                    event.instance_id,
                    event.digest,
                    event.success,
                    event.occurred_at,
                    principal.subject_id,
                    source.fingerprint(),
                ),
            ).fetchone()
            if not added:
                previous = connection.execute(
                    _SQL_RUNTIME_ONE, (principal.tenant_id, event.event_id)
                ).fetchone()
                if not previous or any(previous[key] != value for key, value in expected.items()):
                    raise HTTPException(409, "Runtime observation conflicts with accepted evidence")
        return {"inserted": bool(added)}

    def status(self, principal, at=None):
        """Distinguish fresh drift, failed activation, stale reports and missing coverage."""
        require_admin(principal)
        at = at or datetime.now(UTC)
        result = []
        with self.db.tenant(principal.tenant_id) as connection:
            for source_id, source in self.db.settings.config_sources.items():
                if source.tenant_id != principal.tenant_id:
                    continue
                head = connection.execute(_SQL_HEAD, (principal.tenant_id, source_id)).fetchone()
                valid = (
                    head
                    and head["source_contract"] == source.fingerprint()
                    and not head["error_code"]
                    and (at - head["checked_at"]).total_seconds()
                    <= self.db.settings.config_poll_seconds * 2
                )
                instances = connection.execute(
                    _SQL_RUNTIME,
                    (
                        principal.tenant_id,
                        source_id,
                        source.fingerprint(),
                        self.db.settings.page_size,
                    ),
                ).fetchall()
                for instance in instances:
                    if (
                        at - instance["occurred_at"]
                    ).total_seconds() > self.db.settings.config_runtime_ttl:
                        instance["state"] = "stale"
                    elif not instance["success"]:
                        instance["state"] = "activation_failed"
                    elif not valid:
                        instance["state"] = "source_unavailable"
                    else:
                        instance["state"] = (
                            "matching" if instance["digest"] == head["digest"] else "drift"
                        )
                result.append(
                    {
                        "source_id": source_id,
                        "digest": head["digest"] if valid else None,
                        "checked_at": head["checked_at"] if head else None,
                        "source_state": "current" if valid else "unavailable",
                        "instances": instances,
                        "coverage": "reported_instances_only"
                        if instances
                        else "no_runtime_evidence",
                    }
                )
        return result

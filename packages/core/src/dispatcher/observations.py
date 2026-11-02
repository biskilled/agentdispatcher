"""Correlate overlapping client telemetry without charging an upstream attempt twice."""

import hashlib
from typing import Literal

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import Field

from dispatcher.auth import require_usage_reader, usage_scope, validate_scope
from dispatcher.contracts import Contract, UsageEvent
from dispatcher.source_health import SourceHealth

_SQL_ADD = """
INSERT INTO mem_observations(tenant_id,event_id,service_id,app,environment,expected_source,
correlation_kind,attempt_id,operation_id,payload,evidence_hash,verified_user_id)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id
"""
_SQL_ONE = (
    "SELECT evidence_hash,verified_user_id FROM mem_observations WHERE tenant_id=%s AND event_id=%s"
)
_SQL_SCOPE = "WHERE tenant_id=%s AND (%s OR app=ANY(%s::text[]) OR verified_user_id=%s::uuid)"
_SQL_VISIBLE = (
    """
WITH billable AS (SELECT * FROM mem_usage
"""
    + _SQL_SCOPE
    + """), observed AS (SELECT * FROM mem_observations
"""
    + _SQL_SCOPE
    + """), linked AS (
 SELECT o.*,(SELECT count(*) FROM billable u WHERE u.app=o.app AND u.environment=o.environment
   AND u.payload->>'source'=o.expected_source AND
   ((o.correlation_kind='attempt' AND u.attempt_id=o.attempt_id) OR
    (o.correlation_kind='operation' AND u.payload->>'operation_id'=o.operation_id::text)))
 AS matched_attempts FROM observed o
)
"""
)
_SQL_SUMMARY = (
    _SQL_VISIBLE
    + """
SELECT app,environment,payload->>'source' source,expected_source,correlation_kind,
count(*) observations,count(*) FILTER(WHERE matched_attempts>0) matched,
count(*) FILTER(WHERE matched_attempts=0) missing,max(created_at) last_seen
FROM linked GROUP BY app,environment,payload->>'source',expected_source,correlation_kind
ORDER BY last_seen DESC LIMIT %s
"""
)
_SQL_GAPS = (
    _SQL_VISIBLE
    + """
SELECT event_id,app,environment,expected_source,correlation_kind,attempt_id,operation_id,
payload->>'source' source,payload->>'status' status,created_at
FROM linked WHERE matched_attempts=0 ORDER BY created_at DESC LIMIT %s
"""
)
_SQL_SOURCES = (
    """
SELECT app,environment,payload->>'source' source,payload->>'client_version' client_version,
count(*) attempts,
count(*) FILTER(WHERE cost IS NULL) unknown_cost,max(created_at) last_seen FROM mem_usage
"""
    + _SQL_SCOPE
    + """
GROUP BY app,environment,payload->>'source',payload->>'client_version'
ORDER BY last_seen DESC LIMIT %s
"""
)


class Observation(Contract):
    """A client/transport view references an authoritative source; it cannot create a charge."""

    event: UsageEvent
    expected_source: str = Field(min_length=1, max_length=100)
    correlation_kind: Literal["attempt", "operation"] = "attempt"


class ObservationBatch(Contract):
    """A bounded atomic reference batch uses the same app/environment scope as ingestion."""

    observations: list[Observation] = Field(min_length=1, max_length=1000)


class Observations:
    """References may precede the charge or arrive later; correlation never rewrites prices."""

    def __init__(self, db):
        self.db = db

    def ingest(self, principal, observations):
        """Append metadata-only references and reject altered exports or cross-app claims."""
        for observation in observations:
            validate_scope(principal, observation.event)
        inserted = 0
        with self.db.tenant(principal.tenant_id) as connection:
            for observation in observations:
                event = observation.event.model_copy(update={"tenant_id": principal.tenant_id})
                canonical = observation.model_copy(update={"event": event})
                digest = hashlib.sha256(
                    canonical.model_dump_json(exclude_none=True).encode()
                ).hexdigest()
                added = connection.execute(
                    _SQL_ADD,
                    (
                        principal.tenant_id,
                        event.event_id,
                        principal.subject_id,
                        event.app,
                        event.environment,
                        observation.expected_source,
                        observation.correlation_kind,
                        event.attempt_id,
                        event.operation_id,
                        Jsonb(event.model_dump(mode="json")),
                        digest,
                        principal.verified_user_id,
                    ),
                ).fetchone()
                if not added:
                    previous = connection.execute(
                        _SQL_ONE, (principal.tenant_id, event.event_id)
                    ).fetchone()
                    if (
                        not previous
                        or previous["evidence_hash"] != digest
                        or previous["verified_user_id"] != principal.verified_user_id
                    ):
                        raise HTTPException(409, "Observation conflicts with accepted evidence")
                inserted += bool(added)
        return {"inserted": inserted, "duplicates": len(observations) - inserted}

    def coverage(self, principal):
        """Expose missing upstream evidence without inventing zero costs or provider usage."""
        require_usage_reader(principal)
        scope = (principal.tenant_id, *usage_scope(principal))
        limit = self.db.settings.page_size
        adapters = SourceHealth(self.db).list(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return {
                "adapters": adapters,
                "sources": connection.execute(_SQL_SOURCES, (*scope, limit)).fetchall(),
                "references": connection.execute(_SQL_SUMMARY, (*scope, *scope, limit)).fetchall(),
                "gaps": connection.execute(_SQL_GAPS, (*scope, *scope, limit)).fetchall(),
                "row_limit": limit,
                "coverage": "Observed sources only; uninstrumented applications are not discovered",
            }

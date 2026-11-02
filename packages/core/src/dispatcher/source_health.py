"""Persist safe adapter counters without retaining rejected payloads or credentials."""

from dispatcher.auth import require_usage_reader, usage_scope

_SQL_RECORD = """
INSERT INTO mem_source_health(tenant_id,service_id,app,environment,source,
accepted_exports,rejected_exports,last_error) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT(tenant_id,service_id,source) DO UPDATE SET
accepted_exports=mem_source_health.accepted_exports+EXCLUDED.accepted_exports,
rejected_exports=mem_source_health.rejected_exports+EXCLUDED.rejected_exports,
last_seen=now(),last_error=EXCLUDED.last_error
"""
_SQL_LIST = """
SELECT service_id,app,environment,source,accepted_exports,rejected_exports,last_seen,last_error,
last_seen < now() - %s * interval '1 second' AS stale
FROM mem_source_health WHERE tenant_id=%s AND (%s OR app=ANY(%s::text[]))
ORDER BY last_seen DESC LIMIT %s
"""


class SourceHealth:
    """Adapter health is service-level; it never grants access through app-reported user tags."""

    def __init__(self, db):
        self.db = db

    def record(self, principal, source, accepted, rejected, error=None):
        """Count exports including retries, separately from unique billable attempts."""
        with self.db.tenant(principal.tenant_id) as connection:
            connection.execute(
                _SQL_RECORD,
                (
                    principal.tenant_id,
                    principal.subject_id,
                    principal.app,
                    principal.environment,
                    source,
                    accepted,
                    rejected,
                    error,
                ),
            )

    def list(self, principal):
        """Read only visible app-wide counters; missing heartbeat is not proof of zero usage."""
        require_usage_reader(principal)
        with self.db.tenant(principal.tenant_id) as connection:
            return connection.execute(
                _SQL_LIST,
                (
                    self.db.settings.source_stale_seconds,
                    principal.tenant_id,
                    *usage_scope(principal)[:2],
                    self.db.settings.page_size,
                ),
            ).fetchall()

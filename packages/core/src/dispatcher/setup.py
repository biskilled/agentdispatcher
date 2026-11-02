"""Read-only onboarding evidence; configuration alone never proves an external connection."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends

from dispatcher.auth import require_admin

_SQL_WORKER = "SELECT last_seen FROM mem_worker_health WHERE tenant_id=%s"
_SQL_SOURCES = """
SELECT app,environment,payload->>'source' source,count(*) attempts,
min(created_at) first_seen,max(created_at) last_seen
FROM mem_usage WHERE tenant_id=%s
GROUP BY app,environment,payload->>'source' ORDER BY max(created_at) DESC LIMIT %s
"""


class Setup:
    """Show tenant-scoped first-event evidence without probing providers or exposing secrets."""

    def __init__(self, db):
        self.db = db

    def status(self, principal):
        """Require an administrator because installation and app-wide evidence are privileged."""
        require_admin(principal)
        settings = self.db.settings
        with self.db.tenant(principal.tenant_id) as connection:
            worker = connection.execute(_SQL_WORKER, (principal.tenant_id,)).fetchone()
            sources = connection.execute(
                _SQL_SOURCES, (principal.tenant_id, settings.page_size)
            ).fetchall()
        now = datetime.now(UTC)
        for source in sources:
            source["stale"] = source["last_seen"] < now - timedelta(
                seconds=settings.source_stale_seconds
            )
        return {
            "database_ready": self.db.ready(),
            "worker": {
                "last_seen": worker["last_seen"] if worker else None,
                "healthy": bool(
                    worker
                    and worker["last_seen"]
                    > now - timedelta(seconds=settings.worker_health_ttl_seconds)
                ),
            },
            "configured": {
                "google": bool(
                    settings.google_client_id and settings.google_client_secret.get_secret_value()
                ),
                "email": bool(settings.smtp_host and settings.smtp_sender),
                "gateway": bool(
                    settings.gateway_url and settings.gateway_master_key.get_secret_value()
                ),
                "agentdesk": bool(settings.agentdesk_identity_url),
                "https": settings.public_url.startswith("https://") and settings.secure_cookies,
            },
            "sources": sources,
            "source_limit": settings.page_size,
        }


def routes(db, human):
    """Expose diagnostics only through the normal authenticated tenant boundary."""
    router = APIRouter(prefix="/api/setup")
    setup = Setup(db)

    @router.get("/status")
    def status(principal=Depends(human)):
        """Read local readiness and first-event evidence for this workspace."""
        return setup.status(principal)

    return router

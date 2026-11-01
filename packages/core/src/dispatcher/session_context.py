"""Effective-time attribution snapshots never rewrite previously accepted usage evidence."""

from uuid import UUID

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, Field

from dispatcher.auth import validate_scope
from dispatcher.contracts import Contract

_SQL_ADD = """
INSERT INTO mem_session_context(tenant_id,id,app,environment,session_id,effective_at,
context,service_id)
VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id
"""
_SQL_EXISTING = """
SELECT id,app,environment,session_id,effective_at,context FROM mem_session_context
WHERE tenant_id=%s AND (id=%s OR (app=%s AND environment=%s AND session_id=%s AND effective_at=%s))
"""
_SQL_RESOLVE = """
SELECT context FROM mem_session_context WHERE tenant_id=%s AND app=%s AND environment=%s
AND session_id=%s AND effective_at<=%s ORDER BY effective_at DESC LIMIT 1
"""


class SessionContext(Contract):
    """An immutable context change from a service authorized for this app and environment."""

    id: UUID
    app: str = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=50)
    session_id: str = Field(min_length=1, max_length=100)
    effective_at: AwareDatetime
    project: str | None = Field(default=None, max_length=100)
    work_item: str | None = Field(default=None, max_length=100)
    pipeline_role: str | None = Field(default=None, max_length=100)

    def attributes(self):
        """Only attribution fields are copied; identity and permission claims have no fields."""
        return self.model_dump(include={"project", "work_item", "pipeline_role"})


class SessionContexts:
    """Persist changes independently of usage; missing context remains visibly unknown."""

    def __init__(self, db):
        self.db = db

    def add(self, principal, change):
        """Accept stable replays and reject conflicting changes at the same effective time."""
        validate_scope(principal, change)
        with self.db.tenant(principal.tenant_id) as connection:
            args = (
                principal.tenant_id,
                change.id,
                change.app,
                change.environment,
                change.session_id,
                change.effective_at,
            )
            inserted = connection.execute(
                _SQL_ADD, (*args, Jsonb(change.attributes()), principal.subject_id)
            ).fetchone()
            if not inserted:
                rows = connection.execute(_SQL_EXISTING, args).fetchall()
                expected = change.model_dump(exclude={"project", "work_item", "pipeline_role"})
                expected["context"] = change.attributes()
                if not rows or any(row != expected for row in rows):
                    raise HTTPException(409, "Session context conflicts with accepted evidence")
        return {"inserted": bool(inserted)}


def attributes_at(connection, principal, event):
    """Resolve only absent event attributes, within authenticated scope and the event's time."""
    if not event.session_id:
        return {}
    row = connection.execute(
        _SQL_RESOLVE,
        (principal.tenant_id, event.app, event.environment, event.session_id, event.occurred_at),
    ).fetchone()
    return (
        {
            name: value
            for name, value in row["context"].items()
            if name not in event.model_fields_set
        }
        if row
        else {}
    )

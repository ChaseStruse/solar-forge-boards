"""Activity-event persistence operations."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import Connection, Result, insert, select

from backend.app.models import ActivityRow, activity_events


def create_activity_event(connection: Connection, values: dict[str, Any]) -> ActivityRow:
    """Insert and return an immutable activity event."""
    result: Result[Any] = connection.execute(
        insert(activity_events).values(**values).returning(activity_events)
    )
    return cast(ActivityRow, dict(result.mappings().one()))


def list_activity_events(
    connection: Connection, project_id: UUID, *, limit: int = 50
) -> list[ActivityRow]:
    """Return recent activity for one project, newest first."""
    query: Any = (
        select(activity_events)
        .where(activity_events.c.project_id == project_id)
        .order_by(activity_events.c.created_at.desc())
        .limit(limit)
    )
    result: Result[Any] = connection.execute(query)
    return [cast(ActivityRow, dict(row)) for row in result.mappings().all()]

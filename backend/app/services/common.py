"""Shared transaction and write preconditions for service use cases."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine

from backend.app.correlation import correlation_id
from backend.app.errors import AppError, version_conflict
from backend.app.models import ActivityRow, ProjectRow
from backend.app.repositories import activity as activity_repository


@contextmanager
def transaction(database: Engine | Connection) -> Iterator[Connection]:
    """Own a transaction or participate in an enclosing service transaction."""
    if isinstance(database, Connection):
        yield database
    else:
        with database.begin() as connection:
            yield connection


def require_active_project(project: ProjectRow) -> None:
    """Reject changes to archived history consistently across resources."""
    if project["archived_at"] is not None:
        raise AppError("project_archived", "Archived projects are read-only.", 409)


def require_version(actual: int, expected: int | None) -> None:
    """Check conditional requests even when the requested operation is a no-op."""
    if expected is not None and actual != expected:
        raise version_conflict()


def record_activity(connection: Connection, values: dict[str, Any]) -> ActivityRow:
    """Attach the current trace without changing event transaction boundaries."""
    trace = correlation_id.get()
    if trace is not None:
        values = {**values, "details": {**values["details"], "correlation_id": trace}}
    return activity_repository.create_activity_event(connection, values)

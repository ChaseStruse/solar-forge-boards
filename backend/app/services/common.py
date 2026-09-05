"""Shared transaction and write preconditions for service use cases."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine

from backend.app.errors import AppError, version_conflict
from backend.app.models import ProjectRow


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

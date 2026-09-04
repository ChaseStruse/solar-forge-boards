"""Project persistence operations."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import Connection, Result, delete, insert, select

from backend.app.models import ProjectRow, projects


def create_project(connection: Connection, values: dict[str, Any]) -> ProjectRow:
    """Insert and return a project."""
    result: Result[Any] = connection.execute(insert(projects).values(**values).returning(projects))
    return cast(ProjectRow, dict(result.mappings().one()))


def list_projects(connection: Connection) -> list[ProjectRow]:
    """Return projects in creation order."""
    result: Result[Any] = connection.execute(select(projects).order_by(projects.c.created_at))
    return [cast(ProjectRow, dict(row)) for row in result.mappings().all()]


def get_project(connection: Connection, project_id: UUID) -> ProjectRow | None:
    """Return a project by identifier."""
    result: Result[Any] = connection.execute(select(projects).where(projects.c.id == project_id))
    row: Any = result.mappings().one_or_none()
    return cast(ProjectRow, dict(row)) if row is not None else None


def delete_project(connection: Connection, project_id: UUID) -> None:
    """Delete a project; intended for test cleanup and future lifecycle use."""
    connection.execute(delete(projects).where(projects.c.id == project_id))

"""Project use cases."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from backend.app.errors import AppError, not_found, version_conflict
from backend.app.models import ActivityRow, ProjectRow
from backend.app.repositories import activity as activity_repository
from backend.app.repositories import projects as project_repository
from backend.app.schemas.projects import ProjectCreate, ProjectUpdate
from backend.app.services import tags as tag_service


def create_project(engine: Engine, command: ProjectCreate) -> ProjectRow:
    """Create a project and its initial activity event atomically."""
    project_id: UUID = uuid4()
    try:
        with engine.begin() as connection:
            project: ProjectRow = project_repository.create_project(
                connection,
                {
                    "id": project_id,
                    "name": command.name,
                    "description": command.description,
                },
            )
            tag_service.create_default_tags(connection, project_id)
            activity_repository.create_activity_event(
                connection,
                {
                    "id": uuid4(),
                    "project_id": project_id,
                    "work_item_id": None,
                    "event_type": "project.created",
                    "details": {"name": command.name},
                },
            )
            return project
    except IntegrityError as error:
        raise AppError(
            "project_name_conflict",
            f"A project named '{command.name}' already exists.",
            409,
        ) from error


def list_projects(engine: Engine) -> list[ProjectRow]:
    """List all projects."""
    with engine.connect() as connection:
        return project_repository.list_projects(connection)


def get_project(engine: Engine, project_id: UUID, *, html: bool = False) -> ProjectRow:
    """Get one project or raise a public not-found error."""
    with engine.connect() as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
    if project is None:
        raise not_found("Project", str(project_id), html=html)
    return project


def update_project(
    engine: Engine,
    project_id: UUID,
    command: ProjectUpdate,
    *,
    expected_version: int | None = None,
) -> ProjectRow:
    """Update project details and retain an auditable record of meaningful changes."""
    try:
        with engine.begin() as connection:
            existing: ProjectRow | None = project_repository.get_project(connection, project_id)
            if existing is None:
                raise not_found("Project", str(project_id))
            require_active_project(existing)
            changes: dict[str, Any] = {}
            event_changes: dict[str, dict[str, str]] = {}
            for field_name in ("name", "description"):
                new_value: str | None = getattr(command, field_name)
                old_value: str = existing[field_name]
                if new_value is not None and new_value != old_value:
                    changes[field_name] = new_value
                    event_changes[field_name] = {"from": old_value, "to": new_value}
            if not changes:
                return existing
            changes["updated_at"] = datetime.now(UTC)
            changes["version"] = existing["version"] + 1
            updated: ProjectRow | None = project_repository.update_project(
                connection, project_id, changes, expected_version=expected_version
            )
            if updated is None:
                if expected_version is not None:
                    raise version_conflict()
                raise not_found("Project", str(project_id))
            activity_repository.create_activity_event(
                connection,
                {
                    "id": uuid4(),
                    "project_id": project_id,
                    "work_item_id": None,
                    "event_type": "project.updated",
                    "details": {"changes": event_changes},
                },
            )
            return updated
    except IntegrityError as error:
        raise AppError(
            "project_name_conflict",
            f"A project named '{command.name}' already exists.",
            409,
        ) from error


def archive_project(
    engine: Engine, project_id: UUID, *, expected_version: int | None = None
) -> ProjectRow:
    """Archive a project, preserving all of its data as read-only history."""
    return set_project_archived(
        engine, project_id, archived=True, expected_version=expected_version
    )


def restore_project(
    engine: Engine, project_id: UUID, *, expected_version: int | None = None
) -> ProjectRow:
    """Restore an archived project to active planning."""
    return set_project_archived(
        engine, project_id, archived=False, expected_version=expected_version
    )


def set_project_archived(
    engine: Engine,
    project_id: UUID,
    *,
    archived: bool,
    expected_version: int | None = None,
) -> ProjectRow:
    """Set the reversible project archive state and emit an activity event when it changes."""
    with engine.begin() as connection:
        existing: ProjectRow | None = project_repository.get_project(connection, project_id)
        if existing is None:
            raise not_found("Project", str(project_id))
        currently_archived: bool = existing["archived_at"] is not None
        if currently_archived == archived:
            return existing
        archived_at: datetime | None = datetime.now(UTC) if archived else None
        updated: ProjectRow | None = project_repository.update_project(
            connection,
            project_id,
            {
                "archived_at": archived_at,
                "updated_at": datetime.now(UTC),
                "version": existing["version"] + 1,
            },
            expected_version=expected_version,
        )
        if updated is None:
            if expected_version is not None:
                raise version_conflict()
            raise not_found("Project", str(project_id))
        activity_repository.create_activity_event(
            connection,
            {
                "id": uuid4(),
                "project_id": project_id,
                "work_item_id": None,
                "event_type": "project.archived" if archived else "project.restored",
                "details": {"name": existing["name"]},
            },
        )
        return updated


def require_active_project(project: ProjectRow) -> None:
    """Prevent domain writes against archived projects."""
    if project["archived_at"] is not None:
        raise AppError("project_archived", "Archived projects are read-only.", 409)


def list_project_activity(engine: Engine, project_id: UUID) -> list[ActivityRow]:
    """List recent project activity after confirming the project exists."""
    with engine.connect() as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
        if project is None:
            raise not_found("Project", str(project_id))
        return activity_repository.list_activity_events(connection, project_id)

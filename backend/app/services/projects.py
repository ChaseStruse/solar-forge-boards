"""Project use cases."""

from uuid import UUID, uuid4

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from backend.app.errors import AppError, not_found
from backend.app.models import ActivityRow, ProjectRow
from backend.app.repositories import activity as activity_repository
from backend.app.repositories import projects as project_repository
from backend.app.schemas.projects import ProjectCreate
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


def list_project_activity(engine: Engine, project_id: UUID) -> list[ActivityRow]:
    """List recent project activity after confirming the project exists."""
    with engine.connect() as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
        if project is None:
            raise not_found("Project", str(project_id))
        return activity_repository.list_activity_events(connection, project_id)

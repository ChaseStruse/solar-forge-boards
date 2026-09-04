"""Project-tag use cases and seeded taxonomy."""

from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine

from backend.app.errors import AppError, not_found
from backend.app.models import ProjectRow, TagRow
from backend.app.repositories import activity as activity_repository
from backend.app.repositories import projects as project_repository
from backend.app.repositories import tags as tag_repository
from backend.app.schemas.tags import TagCreate

DEFAULT_TAGS: tuple[tuple[str, str], ...] = (
    ("Business", "#ff5fa2"),
    ("Coding", "#63f5c4"),
    ("Configuration", "#6aa9ff"),
    ("Spike", "#aa7cff"),
)


def create_default_tags(connection: Connection, project_id: UUID) -> list[TagRow]:
    """Seed the standard Solar Forge story taxonomy for a new project."""
    return [
        tag_repository.create_tag(
            connection,
            {"id": uuid4(), "project_id": project_id, "name": name, "color": color},
        )
        for name, color in DEFAULT_TAGS
    ]


def create_tag(engine: Engine, project_id: UUID, command: TagCreate) -> TagRow:
    """Create a case-insensitively unique tag within a project."""
    with engine.begin() as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
        if project is None:
            raise not_found("Project", str(project_id))
        if project["archived_at"] is not None:
            raise AppError("project_archived", "Archived projects are read-only.", 409)
        existing: list[TagRow] = tag_repository.list_project_tags(connection, project_id)
        if any(tag["name"].casefold() == command.name.casefold() for tag in existing):
            raise AppError(
                "tag_name_conflict",
                f"A tag named '{command.name}' already exists in this project.",
                409,
            )
        tag: TagRow = tag_repository.create_tag(
            connection,
            {
                "id": uuid4(),
                "project_id": project_id,
                "name": command.name,
                "color": command.color,
            },
        )
        activity_repository.create_activity_event(
            connection,
            {
                "id": uuid4(),
                "project_id": project_id,
                "work_item_id": None,
                "event_type": "tag.created",
                "details": {"tag_id": str(tag["id"]), "name": tag["name"], "color": tag["color"]},
            },
        )
        return tag


def list_project_tags(engine: Engine, project_id: UUID) -> list[TagRow]:
    """List tags after confirming their project exists."""
    with engine.connect() as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
        if project is None:
            raise not_found("Project", str(project_id))
        return tag_repository.list_project_tags(connection, project_id)

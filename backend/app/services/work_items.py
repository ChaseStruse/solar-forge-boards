"""Work-item use cases and lifecycle rules."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine

from backend.app.domain import WorkItemStatus, can_transition
from backend.app.errors import AppError, not_found
from backend.app.models import ProjectRow, TagRow, WorkItemRow, WorkItemWithTagsRow
from backend.app.repositories import activity as activity_repository
from backend.app.repositories import projects as project_repository
from backend.app.repositories import tags as tag_repository
from backend.app.repositories import work_items as work_item_repository
from backend.app.schemas.work_items import (
    PriorityMove,
    StatusTransition,
    WorkItemCreate,
    WorkItemUpdate,
)


def create_work_item(
    engine: Engine, project_id: UUID, command: WorkItemCreate
) -> WorkItemWithTagsRow:
    """Create a work item and activity event in one transaction."""
    work_item_id: UUID = uuid4()
    with engine.begin() as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
        if project is None:
            raise not_found("Project", str(project_id))
        ensure_project_is_active(project)
        selected_tags: list[TagRow] = validate_tags(connection, project_id, command.tag_ids)
        item: WorkItemRow = work_item_repository.create_work_item(
            connection,
            {
                "id": work_item_id,
                "reference_number": work_item_repository.next_reference_number(connection),
                "project_id": project_id,
                "title": command.title,
                "description": command.description,
                "technical_description": command.technical_description,
                "repository_url": command.repository_url,
                "acceptance_criteria": command.acceptance_criteria,
                "status": WorkItemStatus.TODO.value,
                "priority": work_item_repository.next_priority(
                    connection, project_id, WorkItemStatus.TODO.value
                ),
            },
        )
        tag_repository.replace_work_item_tags(
            connection, work_item_id, [tag["id"] for tag in selected_tags]
        )
        activity_repository.create_activity_event(
            connection,
            {
                "id": uuid4(),
                "project_id": project_id,
                "work_item_id": work_item_id,
                "event_type": "work_item.created",
                "details": {
                    "title": command.title,
                    "status": WorkItemStatus.TODO.value,
                    "tags": [tag["name"] for tag in selected_tags],
                    "acceptance_criteria": command.acceptance_criteria,
                },
            },
        )
        return enrich_work_item(item, selected_tags)


def list_work_items(
    engine: Engine,
    project_id: UUID,
    *,
    filter_tag_ids: list[UUID] | None = None,
    search: str | None = None,
    sort: str = "priority",
    direction: str = "asc",
) -> list[WorkItemWithTagsRow]:
    """List work items after confirming their project exists."""
    with engine.connect() as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
        if project is None:
            raise not_found("Project", str(project_id))
        items: list[WorkItemRow] = work_item_repository.list_work_items(
            connection, project_id, search=search, sort=sort, direction=direction
        )
        enriched: list[WorkItemWithTagsRow] = enrich_work_items(connection, items)
        if not filter_tag_ids:
            return enriched
        selected_tags: list[TagRow] = validate_tags(connection, project_id, filter_tag_ids)
        selected_ids: set[UUID] = {tag["id"] for tag in selected_tags}
        return [item for item in enriched if any(tag["id"] in selected_ids for tag in item["tags"])]


def get_work_item(engine: Engine, work_item_id: UUID) -> WorkItemWithTagsRow:
    """Get one work item or raise not found."""
    with engine.connect() as connection:
        item: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if item is None:
            raise not_found("Work item", str(work_item_id))
        return enrich_work_items(connection, [item])[0]


def get_work_item_by_reference_number(engine: Engine, reference_number: int) -> WorkItemWithTagsRow:
    """Get a story by the number people can use in conversations and pull requests."""
    with engine.connect() as connection:
        item: WorkItemRow | None = work_item_repository.get_work_item_by_reference_number(
            connection, reference_number
        )
        if item is None:
            raise not_found("Work item", f"#{reference_number}")
        return enrich_work_items(connection, [item])[0]


def delete_work_item(engine: Engine, work_item_id: UUID) -> UUID:
    """Delete one work item while retaining an audit event for its project."""
    with engine.begin() as connection:
        existing: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if existing is None:
            raise not_found("Work item", str(work_item_id))
        ensure_work_item_project_is_active(connection, existing)
        deleted: bool = work_item_repository.delete_work_item(connection, work_item_id)
        if not deleted:
            raise not_found("Work item", str(work_item_id))
        activity_repository.create_activity_event(
            connection,
            {
                "id": uuid4(),
                "project_id": existing["project_id"],
                "work_item_id": None,
                "event_type": "work_item.deleted",
                "details": {
                    "work_item_id": str(work_item_id),
                    "title": existing["title"],
                    "status": existing["status"],
                },
            },
        )
        return existing["project_id"]


def update_work_item(
    engine: Engine, work_item_id: UUID, command: WorkItemUpdate
) -> WorkItemWithTagsRow:
    """Update editable fields and record exactly what changed."""
    with engine.begin() as connection:
        existing: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if existing is None:
            raise not_found("Work item", str(work_item_id))
        ensure_work_item_project_is_active(connection, existing)

        changes: dict[str, Any] = {}
        event_changes: dict[str, dict[str, str]] = {}
        for field_name in (
            "title",
            "description",
            "technical_description",
            "repository_url",
            "acceptance_criteria",
        ):
            new_value: Any = getattr(command, field_name)
            old_value: Any = existing[field_name]
            if new_value is not None and new_value != old_value:
                changes[field_name] = new_value
                event_changes[field_name] = {"from": old_value, "to": new_value}

        existing_tags: list[TagRow] = enrich_work_items(connection, [existing])[0]["tags"]
        selected_tags: list[TagRow] = existing_tags
        tags_changed: bool = False
        if command.tag_ids is not None:
            selected_tags = validate_tags(connection, existing["project_id"], command.tag_ids)
            old_tag_ids: set[UUID] = {tag["id"] for tag in existing_tags}
            new_tag_ids: set[UUID] = {tag["id"] for tag in selected_tags}
            tags_changed = old_tag_ids != new_tag_ids
            if tags_changed:
                event_changes["tags"] = {
                    "from": ", ".join(tag["name"] for tag in existing_tags),
                    "to": ", ".join(tag["name"] for tag in selected_tags),
                }

        if not changes and not tags_changed:
            return enrich_work_item(existing, existing_tags)
        changes["updated_at"] = datetime.now(UTC)
        updated: WorkItemRow | None = work_item_repository.update_work_item(
            connection, work_item_id, changes
        )
        if updated is None:
            raise not_found("Work item", str(work_item_id))
        if tags_changed:
            tag_repository.replace_work_item_tags(
                connection, work_item_id, [tag["id"] for tag in selected_tags]
            )
        activity_repository.create_activity_event(
            connection,
            {
                "id": uuid4(),
                "project_id": existing["project_id"],
                "work_item_id": work_item_id,
                "event_type": "work_item.updated",
                "details": {"changes": event_changes},
            },
        )
        return enrich_work_item(updated, selected_tags)


def transition_work_item(
    engine: Engine, work_item_id: UUID, command: StatusTransition
) -> WorkItemWithTagsRow:
    """Apply a valid lifecycle transition and record it."""
    with engine.begin() as connection:
        existing: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if existing is None:
            raise not_found("Work item", str(work_item_id))
        ensure_work_item_project_is_active(connection, existing)
        current: WorkItemStatus = WorkItemStatus(str(existing["status"]))
        target: WorkItemStatus = command.status
        if current == target:
            return enrich_work_items(connection, [existing])[0]
        if not can_transition(current, target):
            raise AppError(
                "invalid_status_transition",
                f"Cannot transition work item from '{current.value}' to '{target.value}'.",
                409,
                details={"current": current.value, "target": target.value},
            )
        updated: WorkItemRow | None = work_item_repository.update_work_item(
            connection,
            work_item_id,
            {
                "status": target.value,
                "priority": work_item_repository.next_priority(
                    connection, existing["project_id"], target.value
                ),
                "updated_at": datetime.now(UTC),
            },
        )
        if updated is None:
            raise not_found("Work item", str(work_item_id))
        activity_repository.create_activity_event(
            connection,
            {
                "id": uuid4(),
                "project_id": existing["project_id"],
                "work_item_id": work_item_id,
                "event_type": "work_item.status_changed",
                "details": {"from": current.value, "to": target.value},
            },
        )
        return enrich_work_items(connection, [updated])[0]


def move_work_item_priority(
    engine: Engine, work_item_id: UUID, command: PriorityMove
) -> WorkItemWithTagsRow:
    """Swap a story with its adjacent priority peer in the current workflow lane."""
    with engine.begin() as connection:
        existing: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if existing is None:
            raise not_found("Work item", str(work_item_id))
        ensure_work_item_project_is_active(connection, existing)
        lane_items: list[WorkItemRow] = work_item_repository.list_work_items_by_status(
            connection, existing["project_id"], existing["status"]
        )
        index: int = next(
            position for position, item in enumerate(lane_items) if item["id"] == work_item_id
        )
        target_index: int = index - 1 if command.direction == "up" else index + 1
        if target_index < 0 or target_index >= len(lane_items):
            return enrich_work_items(connection, [existing])[0]
        neighbor: WorkItemRow = lane_items[target_index]
        now: datetime = datetime.now(UTC)
        moved: WorkItemRow | None = work_item_repository.update_work_item(
            connection, work_item_id, {"priority": neighbor["priority"], "updated_at": now}
        )
        work_item_repository.update_work_item(
            connection, neighbor["id"], {"priority": existing["priority"], "updated_at": now}
        )
        if moved is None:
            raise not_found("Work item", str(work_item_id))
        activity_repository.create_activity_event(
            connection,
            {
                "id": uuid4(),
                "project_id": existing["project_id"],
                "work_item_id": work_item_id,
                "event_type": "work_item.priority_changed",
                "details": {
                    "direction": command.direction,
                    "from": existing["priority"],
                    "to": neighbor["priority"],
                },
            },
        )
        return enrich_work_items(connection, [moved])[0]


def validate_tags(connection: Connection, project_id: UUID, tag_ids: list[UUID]) -> list[TagRow]:
    """Resolve tag IDs and reject tags outside the story's project."""
    selected: list[TagRow] = tag_repository.list_tags_by_ids(connection, project_id, tag_ids)
    if len(selected) != len(tag_ids):
        raise AppError(
            "invalid_story_tags",
            "One or more selected tags do not belong to this project.",
            422,
        )
    return selected


def ensure_project_is_active(project: ProjectRow) -> None:
    """Reject writes into a project retained as read-only history."""
    if project["archived_at"] is not None:
        raise AppError("project_archived", "Archived projects are read-only.", 409)


def ensure_work_item_project_is_active(connection: Connection, item: WorkItemRow) -> None:
    """Resolve a story's project before a write so archived projects cannot change."""
    project: ProjectRow | None = project_repository.get_project(connection, item["project_id"])
    if project is None:
        raise not_found("Project", str(item["project_id"]))
    ensure_project_is_active(project)


def enrich_work_item(item: WorkItemRow, item_tags: list[TagRow]) -> WorkItemWithTagsRow:
    """Attach a tag collection to one repository work-item row."""
    return cast(WorkItemWithTagsRow, {**item, "tags": item_tags})


def enrich_work_items(
    connection: Connection, items: list[WorkItemRow]
) -> list[WorkItemWithTagsRow]:
    """Attach tags to work items with one batch query."""
    tags_by_item: dict[UUID, list[TagRow]] = tag_repository.list_tags_for_work_items(
        connection, [item["id"] for item in items]
    )
    return [enrich_work_item(item, tags_by_item.get(item["id"], [])) for item in items]

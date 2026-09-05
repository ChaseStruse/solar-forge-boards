"""Work-item use cases and lifecycle rules."""

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine

from backend.app.domain import WorkItemStatus, can_transition
from backend.app.errors import AppError, not_found, version_conflict
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
from backend.app.services.common import require_active_project, require_version, transaction


class WorkItemPage(TypedDict):
    """A cursor page of stories and the continuation token, if any."""

    items: list[WorkItemWithTagsRow]
    next_cursor: str | None


def create_work_item(
    engine: Engine | Connection, project_id: UUID, command: WorkItemCreate
) -> WorkItemWithTagsRow:
    """Create a work item and activity event in one transaction."""
    work_item_id: UUID = uuid4()
    with transaction(engine) as connection:
        project: ProjectRow | None = project_repository.get_project(connection, project_id)
        if project is None:
            raise not_found("Project", str(project_id))
        require_active_project(project)
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
        if filter_tag_ids:
            validate_tags(connection, project_id, list(set(filter_tag_ids)))
        items = work_item_repository.list_work_items(
            connection,
            project_id,
            search=search,
            sort=sort,
            direction=direction,
            filter_tag_ids=filter_tag_ids,
        )
        return enrich_work_items(connection, items)


def get_work_item(engine: Engine, work_item_id: UUID) -> WorkItemWithTagsRow:
    """Get one work item or raise not found."""
    with engine.connect() as connection:
        item: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if item is None:
            raise not_found("Work item", str(work_item_id))
        return enrich_work_items(connection, [item])[0]


def list_work_items_page(
    engine: Engine,
    project_id: UUID,
    *,
    filter_tag_ids: list[UUID],
    search: str | None,
    sort: str,
    direction: str,
    limit: int,
    cursor: str | None,
) -> WorkItemPage:
    """Return a stable cursor page for one complete filtered story collection."""
    last_id = (
        decode_cursor(
            cursor,
            search=search,
            filter_tag_ids=filter_tag_ids,
            sort=sort,
            direction=direction,
        )
        if cursor is not None
        else None
    )
    with engine.connect() as connection:
        if project_repository.get_project(connection, project_id) is None:
            raise not_found("Project", str(project_id))
        validate_tags(connection, project_id, list(set(filter_tag_ids)))
        anchor = None
        if last_id is not None:
            anchors = work_item_repository.list_work_items(
                connection,
                project_id,
                search=search,
                sort=sort,
                direction=direction,
                filter_tag_ids=filter_tag_ids,
                work_item_id=last_id,
                limit=1,
            )
            if not anchors:
                raise AppError(
                    "invalid_cursor", "The cursor no longer belongs to this collection.", 422
                )
            anchor = anchors[0]
        items = work_item_repository.list_work_items(
            connection,
            project_id,
            search=search,
            sort=sort,
            direction=direction,
            filter_tag_ids=filter_tag_ids,
            after=anchor,
            limit=limit + 1,
        )
        page_items = enrich_work_items(connection, items[:limit])
    next_cursor = (
        encode_cursor(
            page_items[-1]["id"],
            search=search,
            filter_tag_ids=filter_tag_ids,
            sort=sort,
            direction=direction,
        )
        if len(items) > limit
        else None
    )
    return {"items": page_items, "next_cursor": next_cursor}


def get_work_item_by_reference_number(engine: Engine, reference_number: int) -> WorkItemWithTagsRow:
    """Get a story by the number people can use in conversations and pull requests."""
    with engine.connect() as connection:
        item: WorkItemRow | None = work_item_repository.get_work_item_by_reference_number(
            connection, reference_number
        )
        if item is None:
            raise not_found("Work item", f"#{reference_number}")
        return enrich_work_items(connection, [item])[0]


def delete_work_item(engine: Engine | Connection, work_item_id: UUID) -> UUID:
    """Delete one work item while retaining an audit event for its project."""
    with transaction(engine) as connection:
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
    engine: Engine | Connection,
    work_item_id: UUID,
    command: WorkItemUpdate,
    *,
    expected_version: int | None = None,
) -> WorkItemWithTagsRow:
    """Update editable fields and record exactly what changed."""
    with transaction(engine) as connection:
        existing: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if existing is None:
            raise not_found("Work item", str(work_item_id))
        require_version(existing["version"], expected_version)
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
        changes["version"] = existing["version"] + 1
        updated: WorkItemRow | None = work_item_repository.update_work_item(
            connection, work_item_id, changes, expected_version=expected_version
        )
        if updated is None:
            if expected_version is not None:
                raise version_conflict()
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
    engine: Engine | Connection,
    work_item_id: UUID,
    command: StatusTransition,
    *,
    expected_version: int | None = None,
) -> WorkItemWithTagsRow:
    """Apply a valid lifecycle transition and record it."""
    with transaction(engine) as connection:
        existing: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if existing is None:
            raise not_found("Work item", str(work_item_id))
        require_version(existing["version"], expected_version)
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
                "version": existing["version"] + 1,
            },
            expected_version=expected_version,
        )
        if updated is None:
            if expected_version is not None:
                raise version_conflict()
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
    engine: Engine | Connection,
    work_item_id: UUID,
    command: PriorityMove,
    *,
    expected_version: int | None = None,
) -> WorkItemWithTagsRow:
    """Swap a story with its adjacent priority peer in the current workflow lane."""
    with transaction(engine) as connection:
        existing: WorkItemRow | None = work_item_repository.get_work_item(connection, work_item_id)
        if existing is None:
            raise not_found("Work item", str(work_item_id))
        require_version(existing["version"], expected_version)
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
            connection,
            work_item_id,
            {
                "priority": neighbor["priority"],
                "updated_at": now,
                "version": existing["version"] + 1,
            },
            expected_version=expected_version,
        )
        work_item_repository.update_work_item(
            connection,
            neighbor["id"],
            {
                "priority": existing["priority"],
                "updated_at": now,
                "version": neighbor["version"] + 1,
            },
        )
        if moved is None:
            if expected_version is not None:
                raise version_conflict()
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


def ensure_work_item_project_is_active(connection: Connection, item: WorkItemRow) -> None:
    """Resolve a story's project before a write so archived projects cannot change."""
    project: ProjectRow | None = project_repository.get_project(connection, item["project_id"])
    if project is None:
        raise not_found("Project", str(item["project_id"]))
    require_active_project(project)


def encode_cursor(
    last_id: UUID,
    *,
    search: str | None,
    filter_tag_ids: list[UUID],
    sort: str,
    direction: str,
) -> str:
    """Create an opaque cursor bound to one query's filters and ordering."""
    payload: dict[str, Any] = {
        "v": 1,
        "last_id": str(last_id),
        "search": search,
        "tag_ids": sorted(str(tag_id) for tag_id in set(filter_tag_ids)),
        "sort": sort,
        "direction": direction,
    }
    raw: bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(
    cursor: str,
    *,
    search: str | None,
    filter_tag_ids: list[UUID],
    sort: str,
    direction: str,
) -> UUID:
    """Validate an opaque cursor against the collection query it continues."""
    try:
        padded: str = cursor + "=" * (-len(cursor) % 4)
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
        last_id: UUID = UUID(str(payload["last_id"]))
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AppError("invalid_cursor", "The cursor is invalid.", 422) from error
    expected: dict[str, Any] = {
        "v": 1,
        "search": search,
        "tag_ids": sorted(str(tag_id) for tag_id in set(filter_tag_ids)),
        "sort": sort,
        "direction": direction,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise AppError("invalid_cursor", "The cursor does not match this collection query.", 422)
    return last_id


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

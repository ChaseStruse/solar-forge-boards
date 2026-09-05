"""Project-tag and story-tag persistence operations."""

from collections import defaultdict
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Connection, Result, delete, insert, select

from backend.app.models import TagRow, tags, work_item_tags


def create_tag(connection: Connection, values: dict[str, Any]) -> TagRow:
    """Insert and return a project tag."""
    result: Result[Any] = connection.execute(insert(tags).values(**values).returning(tags))
    return cast(TagRow, dict(result.mappings().one()))


def list_project_tags(connection: Connection, project_id: UUID) -> list[TagRow]:
    """Return a project's tags in stable name order."""
    result: Result[Any] = connection.execute(
        select(tags).where(tags.c.project_id == project_id).order_by(tags.c.name.asc())
    )
    return [cast(TagRow, dict(row)) for row in result.mappings().all()]


def list_tags_by_ids(connection: Connection, project_id: UUID, tag_ids: list[UUID]) -> list[TagRow]:
    """Return matching tags that belong to the requested project."""
    if not tag_ids:
        return []
    result: Result[Any] = connection.execute(
        select(tags)
        .where(tags.c.project_id == project_id, tags.c.id.in_(tag_ids))
        .order_by(tags.c.name.asc())
    )
    return [cast(TagRow, dict(row)) for row in result.mappings().all()]


def list_tags_for_work_items(
    connection: Connection, work_item_ids: list[UUID]
) -> dict[UUID, list[TagRow]]:
    """Batch-load ordered tags for a collection of work items."""
    grouped: defaultdict[UUID, list[TagRow]] = defaultdict(list)
    if not work_item_ids:
        return dict(grouped)
    query: Any = (
        select(work_item_tags.c.work_item_id, tags)
        .join(tags, tags.c.id == work_item_tags.c.tag_id)
        .where(work_item_tags.c.work_item_id.in_(work_item_ids))
        .order_by(tags.c.name.asc())
    )
    result: Result[Any] = connection.execute(query)
    for row in result.mappings().all():
        work_item_id: UUID = row["work_item_id"]
        grouped[work_item_id].append(
            cast(
                TagRow,
                {
                    "id": row["id"],
                    "project_id": row["project_id"],
                    "name": row["name"],
                    "color": row["color"],
                    "created_at": row["created_at"],
                },
            )
        )
    return dict(grouped)


def replace_work_item_tags(connection: Connection, work_item_id: UUID, tag_ids: list[UUID]) -> None:
    """Replace all tags assigned to one work item."""
    connection.execute(delete(work_item_tags).where(work_item_tags.c.work_item_id == work_item_id))
    if tag_ids:
        connection.execute(
            insert(work_item_tags),
            [{"work_item_id": work_item_id, "tag_id": tag_id} for tag_id in tag_ids],
        )

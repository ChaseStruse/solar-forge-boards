"""Work-item persistence operations."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import Connection, Result, delete, insert, select, update

from backend.app.models import WorkItemRow, work_items


def create_work_item(connection: Connection, values: dict[str, Any]) -> WorkItemRow:
    """Insert and return a work item."""
    result: Result[Any] = connection.execute(
        insert(work_items).values(**values).returning(work_items)
    )
    return cast(WorkItemRow, dict(result.mappings().one()))


def list_work_items(connection: Connection, project_id: UUID) -> list[WorkItemRow]:
    """Return work items for one project in creation order."""
    query: Any = (
        select(work_items)
        .where(work_items.c.project_id == project_id)
        .order_by(work_items.c.created_at)
    )
    result: Result[Any] = connection.execute(query)
    return [cast(WorkItemRow, dict(row)) for row in result.mappings().all()]


def get_work_item(connection: Connection, work_item_id: UUID) -> WorkItemRow | None:
    """Return a work item by identifier."""
    result: Result[Any] = connection.execute(
        select(work_items).where(work_items.c.id == work_item_id)
    )
    row: Any = result.mappings().one_or_none()
    return cast(WorkItemRow, dict(row)) if row is not None else None


def update_work_item(
    connection: Connection, work_item_id: UUID, values: dict[str, Any]
) -> WorkItemRow | None:
    """Update and return a work item."""
    result: Result[Any] = connection.execute(
        update(work_items)
        .where(work_items.c.id == work_item_id)
        .values(**values)
        .returning(work_items)
    )
    row: Any = result.mappings().one_or_none()
    return cast(WorkItemRow, dict(row)) if row is not None else None


def delete_work_item(connection: Connection, work_item_id: UUID) -> bool:
    """Delete a work item and report whether a row was removed."""
    result: Result[Any] = connection.execute(
        delete(work_items).where(work_items.c.id == work_item_id).returning(work_items.c.id)
    )
    return result.scalar_one_or_none() is not None

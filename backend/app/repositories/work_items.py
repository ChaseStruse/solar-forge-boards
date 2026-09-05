"""Work-item persistence operations."""

from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    Connection,
    Result,
    and_,
    asc,
    delete,
    desc,
    func,
    insert,
    or_,
    select,
    update,
)

from backend.app.models import WorkItemRow, work_items


def create_work_item(connection: Connection, values: dict[str, Any]) -> WorkItemRow:
    """Insert and return a work item."""
    result: Result[Any] = connection.execute(
        insert(work_items).values(**values).returning(work_items)
    )
    return cast(WorkItemRow, dict(result.mappings().one()))


def list_work_items(
    connection: Connection,
    project_id: UUID,
    *,
    search: str | None = None,
    sort: str = "created_at",
    direction: str = "asc",
) -> list[WorkItemRow]:
    """Return filtered, ordered work items for one project."""
    sort_columns: dict[str, Any] = {
        "created_at": work_items.c.created_at,
        "updated_at": work_items.c.updated_at,
        "title": work_items.c.title,
        "status": work_items.c.status,
        "priority": work_items.c.priority,
    }
    sort_column: Any = sort_columns[sort]
    order: Any = desc(sort_column) if direction == "desc" else asc(sort_column)
    query: Any = (
        select(work_items)
        .where(work_items.c.project_id == project_id)
        .order_by(order, work_items.c.id)
    )
    if search:
        pattern: str = f"%{search.casefold()}%"
        query = query.where(
            or_(
                work_items.c.title.ilike(pattern),
                work_items.c.description.ilike(pattern),
                work_items.c.technical_description.ilike(pattern),
            )
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


def get_work_item_by_reference_number(
    connection: Connection, reference_number: int
) -> WorkItemRow | None:
    """Return a work item by its human-friendly global reference number."""
    result: Result[Any] = connection.execute(
        select(work_items).where(work_items.c.reference_number == reference_number)
    )
    row: Any = result.mappings().one_or_none()
    return cast(WorkItemRow, dict(row)) if row is not None else None


def next_reference_number(connection: Connection) -> int:
    """Return the next global story reference number."""
    result: Result[Any] = connection.execute(
        select(func.coalesce(func.max(work_items.c.reference_number), 0) + 1)
    )
    return int(result.scalar_one())


def list_work_items_by_status(
    connection: Connection, project_id: UUID, status: str
) -> list[WorkItemRow]:
    """Return one lane's stories in their persisted priority order."""
    result: Result[Any] = connection.execute(
        select(work_items)
        .where(work_items.c.project_id == project_id, work_items.c.status == status)
        .order_by(work_items.c.priority, work_items.c.id)
    )
    return [cast(WorkItemRow, dict(row)) for row in result.mappings().all()]


def next_priority(connection: Connection, project_id: UUID, status: str) -> int:
    """Return the next position at the end of a project's workflow lane."""
    result: Result[Any] = connection.execute(
        select(func.coalesce(func.max(work_items.c.priority), 0) + 1).where(
            work_items.c.project_id == project_id, work_items.c.status == status
        )
    )
    return int(result.scalar_one())


def update_work_item(
    connection: Connection,
    work_item_id: UUID,
    values: dict[str, Any],
    *,
    expected_version: int | None = None,
) -> WorkItemRow | None:
    """Update and return a work item."""
    conditions: list[Any] = [work_items.c.id == work_item_id]
    if expected_version is not None:
        conditions.append(work_items.c.version == expected_version)
    result: Result[Any] = connection.execute(
        update(work_items).where(and_(*conditions)).values(**values).returning(work_items)
    )
    row: Any = result.mappings().one_or_none()
    return cast(WorkItemRow, dict(row)) if row is not None else None


def delete_work_item(connection: Connection, work_item_id: UUID) -> bool:
    """Delete a work item and report whether a row was removed."""
    result: Result[Any] = connection.execute(
        delete(work_items).where(work_items.c.id == work_item_id).returning(work_items.c.id)
    )
    return result.scalar_one_or_none() is not None

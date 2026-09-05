"""Outbox persistence; callers own transactions, delivery policy, and network I/O."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Connection, and_, insert, or_, select, text, update

from backend.app.models import OutboxRow, outbox_events


def enqueue(connection: Connection, values: dict[str, Any]) -> None:
    """Insert one event; PostgreSQL delivers its wake-up only after commit."""
    connection.execute(insert(outbox_events).values(**values))
    notify(connection)


def notify(connection: Connection) -> None:
    """Wake dispatchers without placing sensitive payloads on the notification channel."""
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_notify('solar_forge_outbox', '')"))


def get_event(connection: Connection, event_id: UUID) -> OutboxRow | None:
    row = (
        connection.execute(select(outbox_events).where(outbox_events.c.id == event_id))
        .mappings()
        .one_or_none()
    )
    return cast(OutboxRow, dict(row)) if row else None


def list_events(
    connection: Connection,
    project_id: UUID,
    status: str | None,
    limit: int,
) -> list[OutboxRow]:
    query = select(outbox_events).where(outbox_events.c.project_id == project_id)
    if status is not None:
        query = query.where(outbox_events.c.status == status)
    rows = connection.execute(
        query.order_by(outbox_events.c.created_at.desc(), outbox_events.c.id.desc()).limit(limit)
    ).mappings()
    return [cast(OutboxRow, dict(row)) for row in rows]


def claim(
    connection: Connection,
    now: datetime,
    lease_until: datetime,
    token: UUID,
    event_types: tuple[str, ...],
) -> OutboxRow | None:
    """Lease one due event with row locking and a conditional update fence."""
    table = outbox_events.c
    expired = and_(table.status == "processing", table.lease_until <= now)
    exhausted = update(outbox_events).where(expired, table.attempts >= table.attempt_limit)
    if event_types:
        exhausted = exhausted.where(table.event_type.in_(event_types))
    connection.execute(
        exhausted.values(
            status="failed",
            lease_token=None,
            lease_until=None,
            last_error="Delivery lease expired; attempt limit reached.",
        )
    )
    eligible = and_(
        or_(and_(table.status == "pending", table.next_attempt_at <= now), expired),
        table.attempts < table.attempt_limit,
    )
    query = select(table.id).where(eligible)
    if event_types:
        query = query.where(table.event_type.in_(event_types))
    selected = connection.execute(
        query.order_by(table.next_attempt_at, table.id).limit(1).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if selected is None:
        return None
    row = (
        connection.execute(
            update(outbox_events)
            .where(table.id == selected, eligible)
            .values(
                status="processing",
                attempts=table.attempts + 1,
                lease_token=token,
                lease_until=lease_until,
            )
            .returning(outbox_events)
        )
        .mappings()
        .one_or_none()
    )
    return cast(OutboxRow, dict(row)) if row else None


def finish(connection: Connection, event_id: UUID, token: UUID, values: dict[str, Any]) -> bool:
    """Reject acknowledgements from a worker whose lease has been reclaimed."""
    row = connection.execute(
        update(outbox_events)
        .where(
            outbox_events.c.id == event_id,
            outbox_events.c.status == "processing",
            outbox_events.c.lease_token == token,
        )
        .values(**values, lease_token=None, lease_until=None)
        .returning(outbox_events.c.id)
    ).first()
    return row is not None


def retry(
    connection: Connection, event_id: UUID, now: datetime, attempt_limit: int
) -> OutboxRow | None:
    """Requeue failed delivery without resetting lifetime attempt history or changing the ID."""
    row = (
        connection.execute(
            update(outbox_events)
            .where(
                outbox_events.c.id == event_id,
                outbox_events.c.status == "failed",
            )
            .values(
                status="pending",
                attempt_limit=attempt_limit,
                next_attempt_at=now,
                lease_token=None,
                lease_until=None,
            )
            .returning(outbox_events)
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        notify(connection)
        return cast(OutboxRow, dict(row))
    return None

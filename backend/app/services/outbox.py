"""Durable at-least-once delivery, bounded retries, and operator recovery."""

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine

from backend.app.errors import AppError, not_found
from backend.app.models import OutboxRow
from backend.app.repositories import outbox as repository
from backend.app.repositories import projects as project_repository
from backend.app.services.common import transaction


class Sender(Protocol):
    def send(self, event: OutboxRow) -> str | None:
        """Return a sanitized failure string, or None after receiver acknowledgement."""
        ...


def get_event(engine: Engine, event_id: UUID) -> OutboxRow:
    with engine.connect() as connection:
        event = repository.get_event(connection, event_id)
    if event is None:
        raise not_found("Outbox event", str(event_id))
    return event


def list_events(
    engine: Engine,
    project_id: UUID,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[OutboxRow]:
    with engine.connect() as connection:
        if project_repository.get_project(connection, project_id) is None:
            raise not_found("Project", str(project_id))
        return repository.list_events(connection, project_id, status, limit)


def retry_event(engine: Engine | Connection, event_id: UUID) -> OutboxRow:
    """Only failed deliveries can be explicitly retried, including archived project history."""
    with transaction(engine) as connection:
        event = repository.get_event(connection, event_id)
        if event is None:
            raise not_found("Outbox event", str(event_id))
        retried = repository.retry(connection, event_id, datetime.now(UTC), event["attempts"] + 8)
        if retried is None:
            raise AppError("outbox_not_failed", "Only failed deliveries can be retried.", 409)
        return retried


def deliver_one(
    engine: Engine,
    sender: Sender,
    *,
    event_types: tuple[str, ...] = (),
    now: datetime | None = None,
) -> bool:
    """Commit a claim, deliver without a database lock, then fence the acknowledgement."""
    started = now or datetime.now(UTC)
    token = uuid4()
    with engine.begin() as connection:
        event = repository.claim(
            connection, started, started + timedelta(seconds=60), token, event_types
        )
    if event is None:
        return False
    # Unexpected sender failures leave the lease recoverable instead of losing the event.
    error = sender.send(event)
    finished = now or datetime.now(UTC)
    values: dict[str, Any]
    if error is None:
        values = {"status": "delivered", "delivered_at": finished, "last_error": None}
    else:
        values = {
            "status": "failed" if event["attempts"] >= event["attempt_limit"] else "pending",
            "last_error": error[:255],
            "next_attempt_at": finished
            + timedelta(seconds=min(3600, 5 * 2 ** min(event["attempts"] - 1, 10))),
        }
    with engine.begin() as connection:
        repository.finish(connection, event["id"], token, values)
    return True

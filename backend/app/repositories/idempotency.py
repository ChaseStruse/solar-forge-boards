"""Persistence operations for replay-safe API writes."""

from typing import Any, cast

from sqlalchemy import Connection, Result, delete, insert, select, update

from backend.app.models import IdempotencyRequestRow, idempotency_requests


def get_request(connection: Connection, key: str) -> IdempotencyRequestRow | None:
    """Return a request record by its client-supplied idempotency key."""
    result: Result[Any] = connection.execute(
        select(idempotency_requests).where(idempotency_requests.c.key == key)
    )
    row: Any = result.mappings().one_or_none()
    return cast(IdempotencyRequestRow, dict(row)) if row is not None else None


def create_request(
    connection: Connection, *, key: str, request_scope: str, request_fingerprint: str
) -> None:
    """Reserve an idempotency key before executing its write."""
    connection.execute(
        insert(idempotency_requests).values(
            key=key,
            request_scope=request_scope,
            request_fingerprint=request_fingerprint,
        )
    )


def complete_request(
    connection: Connection, key: str, *, response_status: int, response_data: dict[str, Any]
) -> None:
    """Store the canonical response returned for a completed write."""
    connection.execute(
        update(idempotency_requests)
        .where(idempotency_requests.c.key == key)
        .values(response_status=response_status, response_data=response_data)
    )


def delete_request(connection: Connection, key: str) -> None:
    """Release a reservation when its write did not complete."""
    connection.execute(delete(idempotency_requests).where(idempotency_requests.c.key == key))

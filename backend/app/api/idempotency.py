"""Translate replay headers for the transactional service boundary."""

from collections.abc import Callable

from flask import request
from pydantic import BaseModel
from sqlalchemy import Connection, Engine

from backend.app.services import idempotency


def execute_idempotent[ModelT: BaseModel](
    engine: Engine,
    *,
    scope: str,
    command: BaseModel,
    expected_version: int | None,
    model_type: type[ModelT],
    status: int,
    operation: Callable[[Connection], ModelT],
) -> tuple[ModelT, int]:
    """Pass HTTP metadata to the service that owns the complete write transaction."""
    return idempotency.execute_idempotent(
        engine,
        key=request.headers.get("Idempotency-Key"),
        scope=scope,
        command=command,
        expected_version=expected_version,
        model_type=model_type,
        status=status,
        operation=operation,
    )

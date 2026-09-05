"""Replay protection for public JSON writes."""

import hashlib
import json
from collections.abc import Callable
from typing import Any

from flask import request
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from backend.app.errors import AppError
from backend.app.repositories import idempotency as idempotency_repository


def execute_idempotent[ModelT: BaseModel](
    engine: Engine,
    *,
    scope: str,
    command: BaseModel,
    expected_version: int | None,
    model_type: type[ModelT],
    status: int,
    operation: Callable[[], ModelT],
) -> tuple[ModelT, int]:
    """Execute a write once per key, returning its original response on retries."""
    key: str | None = request.headers.get("Idempotency-Key")
    if key is None:
        return operation(), status
    key = key.strip()
    if not key or len(key) > 255:
        raise AppError(
            "invalid_idempotency_key",
            "Idempotency-Key must contain between 1 and 255 characters.",
            422,
        )
    fingerprint: str = request_fingerprint(command, expected_version)
    try:
        with engine.begin() as connection:
            idempotency_repository.create_request(
                connection, key=key, request_scope=scope, request_fingerprint=fingerprint
            )
    except IntegrityError as error:
        with engine.connect() as connection:
            existing = idempotency_repository.get_request(connection, key)
        if existing is None:
            raise
        if existing["request_scope"] != scope or existing["request_fingerprint"] != fingerprint:
            raise AppError(
                "idempotency_key_reused",
                "Idempotency-Key was already used for a different request.",
                409,
            ) from error
        if existing["response_status"] is None or existing["response_data"] is None:
            raise AppError(
                "idempotency_in_progress",
                "A request with this Idempotency-Key is still being processed.",
                409,
            ) from error
        return model_type.model_validate(existing["response_data"]), existing["response_status"]

    try:
        response_model: ModelT = operation()
        response_data: dict[str, Any] = response_model.model_dump(mode="json")
        with engine.begin() as connection:
            idempotency_repository.complete_request(
                connection, key, response_status=status, response_data=response_data
            )
    except Exception:
        with engine.begin() as connection:
            idempotency_repository.delete_request(connection, key)
        raise
    return response_model, status


def request_fingerprint(command: BaseModel, expected_version: int | None) -> str:
    """Hash canonical validated input, including the conditional revision when supplied."""
    payload: dict[str, Any] = {
        "command": command.model_dump(mode="json"),
        "expected_version": expected_version,
    }
    encoded: bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()

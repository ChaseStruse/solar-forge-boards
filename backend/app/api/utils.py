"""Shared JSON request and response helpers."""

from typing import Any

from flask import Response, jsonify, request
from pydantic import BaseModel

from backend.app.errors import AppError


def parse_json[SchemaT: BaseModel](schema: type[SchemaT]) -> SchemaT:
    """Validate the current JSON request against a Pydantic schema."""
    payload: Any = request.get_json(silent=True)
    return schema.model_validate(payload if payload is not None else {})


def json_model(
    model: BaseModel, *, status: int = 200, etag: int | None = None
) -> tuple[Response, int]:
    """Return a schema in a stable data envelope."""
    response: Response = jsonify({"data": model.model_dump(mode="json")})
    if etag is not None:
        response.set_etag(str(etag))
    return response, status


def parse_if_match() -> int | None:
    """Read one resource revision from a standard quoted ETag precondition header."""
    value: str | None = request.headers.get("If-Match")
    if value is None:
        return None
    if len(value) < 3 or not value.startswith('"') or not value.endswith('"'):
        raise AppError("invalid_if_match", "If-Match must be a quoted positive integer ETag.", 422)
    try:
        version: int = int(value[1:-1])
    except ValueError as error:
        raise AppError(
            "invalid_if_match", "If-Match must be a quoted positive integer ETag.", 422
        ) from error
    if version < 1:
        raise AppError("invalid_if_match", "If-Match must be a quoted positive integer ETag.", 422)
    return version


def json_models(
    models: list[BaseModel], *, next_cursor: str | None = None, include_page_meta: bool = False
) -> Response:
    """Return a list of schemas in a stable data envelope."""
    payload: dict[str, Any] = {"data": [model.model_dump(mode="json") for model in models]}
    if include_page_meta:
        payload["meta"] = {"next_cursor": next_cursor}
    return jsonify(payload)

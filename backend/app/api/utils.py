"""Shared JSON request and response helpers."""

from typing import Any

from flask import Response, jsonify, request
from pydantic import BaseModel


def parse_json[SchemaT: BaseModel](schema: type[SchemaT]) -> SchemaT:
    """Validate the current JSON request against a Pydantic schema."""
    payload: Any = request.get_json(silent=True)
    return schema.model_validate(payload if payload is not None else {})


def json_model(model: BaseModel, *, status: int = 200) -> tuple[Response, int]:
    """Return a schema in a stable data envelope."""
    return jsonify({"data": model.model_dump(mode="json")}), status


def json_models(models: list[BaseModel]) -> Response:
    """Return a list of schemas in a stable data envelope."""
    return jsonify({"data": [model.model_dump(mode="json") for model in models]})

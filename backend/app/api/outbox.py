"""Public delivery diagnostics and explicit failed-event recovery."""

from typing import Any
from uuid import UUID

from flask import Blueprint, Response, request

from backend.app.api.idempotency import execute_idempotent
from backend.app.api.utils import json_model, json_models, parse_json
from backend.app.database import get_engine
from backend.app.schemas.common import ApiModel
from backend.app.schemas.outbox import OutboxFilter, OutboxRead
from backend.app.services import outbox as service

outbox_blueprint = Blueprint("api_outbox", __name__, url_prefix="/api/v1")


def present(row: dict[str, Any]) -> OutboxRead:
    """Exclude the internal lease token from diagnostic responses."""
    return OutboxRead.model_validate(
        {key: value for key, value in row.items() if key != "lease_token"}
    )


@outbox_blueprint.get("/projects/<uuid:project_id>/outbox")
def list_events(project_id: UUID) -> Response:
    filters = OutboxFilter.model_validate(request.args.to_dict())
    events = service.list_events(
        get_engine(), project_id, status=filters.status, limit=filters.limit
    )
    return json_models([present(dict(event)) for event in events])


@outbox_blueprint.get("/outbox/<uuid:event_id>")
def get_event(event_id: UUID) -> tuple[Response, int]:
    return json_model(present(dict(service.get_event(get_engine(), event_id))))


@outbox_blueprint.post("/outbox/<uuid:event_id>/retry")
def retry_event(event_id: UUID) -> tuple[Response, int]:
    command = parse_json(ApiModel)
    event, status = execute_idempotent(
        get_engine(),
        scope=f"POST:/api/v1/outbox/{event_id}/retry",
        command=command,
        expected_version=None,
        model_type=OutboxRead,
        status=200,
        operation=lambda connection: present(dict(service.retry_event(connection, event_id))),
    )
    return json_model(event, status=status)

"""Work-item JSON endpoints."""

from uuid import UUID

from flask import Blueprint, Response

from backend.app.api.utils import json_model, parse_json
from backend.app.database import get_engine
from backend.app.models import WorkItemWithTagsRow
from backend.app.schemas.work_items import (
    PriorityMove,
    StatusTransition,
    WorkItemRead,
    WorkItemUpdate,
)
from backend.app.services import work_items as work_item_service

work_items_blueprint: Blueprint = Blueprint("api_work_items", __name__, url_prefix="/api/v1")


@work_items_blueprint.get("/work-items/by-reference/<int:reference_number>")
def get_work_item_by_reference_number(reference_number: int) -> tuple[Response, int]:
    """Get a work item by its visible human-friendly reference number."""
    item: WorkItemWithTagsRow = work_item_service.get_work_item_by_reference_number(
        get_engine(), reference_number
    )
    return json_model(WorkItemRead.model_validate(item))


@work_items_blueprint.get("/work-items/<uuid:work_item_id>")
def get_work_item(work_item_id: UUID) -> tuple[Response, int]:
    """Get a work item."""
    item: WorkItemWithTagsRow = work_item_service.get_work_item(get_engine(), work_item_id)
    return json_model(WorkItemRead.model_validate(item))


@work_items_blueprint.patch("/work-items/<uuid:work_item_id>")
def update_work_item(work_item_id: UUID) -> tuple[Response, int]:
    """Edit a work item's content."""
    command: WorkItemUpdate = parse_json(WorkItemUpdate)
    item: WorkItemWithTagsRow = work_item_service.update_work_item(
        get_engine(), work_item_id, command
    )
    return json_model(WorkItemRead.model_validate(item))


@work_items_blueprint.delete("/work-items/<uuid:work_item_id>")
def delete_work_item(work_item_id: UUID) -> Response:
    """Permanently delete a work item."""
    work_item_service.delete_work_item(get_engine(), work_item_id)
    return Response(status=204)


@work_items_blueprint.post("/work-items/<uuid:work_item_id>/transitions")
def transition_work_item(work_item_id: UUID) -> tuple[Response, int]:
    """Move a work item through its lifecycle."""
    command: StatusTransition = parse_json(StatusTransition)
    item: WorkItemWithTagsRow = work_item_service.transition_work_item(
        get_engine(), work_item_id, command
    )
    return json_model(WorkItemRead.model_validate(item))


@work_items_blueprint.post("/work-items/<uuid:work_item_id>/priority")
def move_work_item_priority(work_item_id: UUID) -> tuple[Response, int]:
    """Move a story up or down within its current workflow lane."""
    command: PriorityMove = parse_json(PriorityMove)
    item: WorkItemWithTagsRow = work_item_service.move_work_item_priority(
        get_engine(), work_item_id, command
    )
    return json_model(WorkItemRead.model_validate(item))

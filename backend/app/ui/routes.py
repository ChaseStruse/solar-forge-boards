"""HTMX routes that reuse the application service layer."""

from typing import Any
from uuid import UUID

from flask import Blueprint, make_response, redirect, render_template, request, url_for
from pydantic import ValidationError
from werkzeug.wrappers import Response

from backend.app.database import get_engine
from backend.app.domain import ALLOWED_TRANSITIONS, WorkItemStatus
from backend.app.errors import AppError
from backend.app.models import ProjectRow, TagRow, WorkItemWithTagsRow
from backend.app.schemas.projects import ProjectCreate
from backend.app.schemas.tags import TagCreate
from backend.app.schemas.work_items import StatusTransition, WorkItemCreate, WorkItemUpdate
from backend.app.services import projects as project_service
from backend.app.services import tags as tag_service
from backend.app.services import work_items as work_item_service

ui_blueprint: Blueprint = Blueprint("ui", __name__)


@ui_blueprint.get("/")
def index() -> Response:
    """Redirect to the project workspace."""
    return redirect(url_for("ui.projects_page"))


@ui_blueprint.get("/ui/projects")
def projects_page() -> str:
    """Render the project list and create form."""
    projects: list[ProjectRow] = project_service.list_projects(get_engine())
    return render_template("projects.html", projects=projects)


@ui_blueprint.post("/ui/projects")
def create_project() -> tuple[str, int] | Response:
    """Create a project from an HTML form."""
    try:
        command: ProjectCreate = ProjectCreate.model_validate(request.form.to_dict())
        project: ProjectRow = project_service.create_project(get_engine(), command)
    except (ValidationError, AppError) as error:
        projects: list[ProjectRow] = project_service.list_projects(get_engine())
        return render_template("projects.html", projects=projects, form_error=str(error)), 422
    return redirect(url_for("ui.project_board", project_id=project["id"]))


@ui_blueprint.get("/ui/projects/<uuid:project_id>")
def project_board(project_id: UUID) -> str:
    """Render a project's board view."""
    return render_project_board(project_id)


@ui_blueprint.post("/ui/projects/<uuid:project_id>/tags")
def create_project_tag(project_id: UUID) -> tuple[str, int] | Response:
    """Create a custom project tag and return to the board."""
    try:
        command: TagCreate = TagCreate.model_validate(request.form.to_dict())
        tag_service.create_tag(get_engine(), project_id, command)
    except (ValidationError, AppError) as error:
        return render_project_board(project_id, tag_error=str(error)), 422
    return redirect(url_for("ui.project_board", project_id=project_id))


def render_project_board(project_id: UUID, *, tag_error: str | None = None) -> str:
    """Render a board with its complete project tag vocabulary."""
    project: ProjectRow = project_service.get_project(get_engine(), project_id, html=True)
    items: list[WorkItemWithTagsRow] = work_item_service.list_work_items(get_engine(), project_id)
    project_tags: list[TagRow] = tag_service.list_project_tags(get_engine(), project_id)
    return render_template(
        "board.html",
        project=project,
        project_id=project_id,
        grouped_items=group_work_items(items),
        project_tags=project_tags,
        tag_error=tag_error,
        statuses=list(WorkItemStatus),
        allowed_transitions=ALLOWED_TRANSITIONS,
    )


@ui_blueprint.post("/ui/projects/<uuid:project_id>/work-items")
def create_work_item(project_id: UUID) -> tuple[str, int]:
    """Create a card and return a refreshed board fragment."""
    try:
        command: WorkItemCreate = WorkItemCreate.model_validate(form_with_tag_ids())
        work_item_service.create_work_item(get_engine(), project_id, command)
    except (ValidationError, AppError) as error:
        return render_template("partials/form_error.html", message=str(error)), 422
    return render_board_fragment(project_id), 201


@ui_blueprint.post("/ui/work-items/<uuid:work_item_id>/transitions")
def transition_work_item(work_item_id: UUID) -> tuple[str, int]:
    """Transition a card and return a refreshed board fragment."""
    command: StatusTransition = StatusTransition.model_validate(request.form.to_dict())
    item: WorkItemWithTagsRow = work_item_service.transition_work_item(
        get_engine(), work_item_id, command
    )
    return render_board_fragment(UUID(str(item["project_id"]))), 200


@ui_blueprint.post("/ui/work-items/<uuid:work_item_id>")
def update_work_item(work_item_id: UUID) -> tuple[str, int] | Response:
    """Edit a story and return a refreshed board fragment."""
    try:
        command: WorkItemUpdate = WorkItemUpdate.model_validate(form_with_tag_ids())
        item: WorkItemWithTagsRow = work_item_service.update_work_item(
            get_engine(), work_item_id, command
        )
    except (ValidationError, AppError) as error:
        response: Response = make_response(
            render_template("partials/form_error.html", message=str(error)), 422
        )
        response.headers["HX-Retarget"] = f"#edit-error-{work_item_id}"
        response.headers["HX-Reswap"] = "innerHTML"
        return response
    return render_board_fragment(UUID(str(item["project_id"]))), 200


@ui_blueprint.post("/ui/work-items/<uuid:work_item_id>/delete")
def delete_work_item(work_item_id: UUID) -> tuple[str, int]:
    """Delete a story and return its project's refreshed board."""
    project_id: UUID = work_item_service.delete_work_item(get_engine(), work_item_id)
    return render_board_fragment(project_id), 200


def render_board_fragment(project_id: UUID) -> str:
    """Render the board columns for HTMX swaps."""
    items: list[WorkItemWithTagsRow] = work_item_service.list_work_items(get_engine(), project_id)
    project_tags: list[TagRow] = tag_service.list_project_tags(get_engine(), project_id)
    return render_template(
        "partials/board_columns.html",
        project_id=project_id,
        grouped_items=group_work_items(items),
        project_tags=project_tags,
        statuses=list(WorkItemStatus),
        allowed_transitions=ALLOWED_TRANSITIONS,
    )


def group_work_items(
    items: list[WorkItemWithTagsRow],
) -> dict[WorkItemStatus, list[WorkItemWithTagsRow]]:
    """Group work items into ordered status columns."""
    grouped: dict[WorkItemStatus, list[WorkItemWithTagsRow]] = {
        status: [] for status in WorkItemStatus
    }
    for item in items:
        grouped[WorkItemStatus(str(item["status"]))].append(item)
    return grouped


def form_with_tag_ids() -> dict[str, Any]:
    """Preserve repeated tag checkbox values from an HTML form."""
    payload: dict[str, Any] = request.form.to_dict()
    payload["tag_ids"] = request.form.getlist("tag_ids")
    return payload

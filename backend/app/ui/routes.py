"""HTMX routes that reuse the application service layer."""

from typing import Any
from uuid import UUID

from flask import Blueprint, current_app, make_response, redirect, render_template, request, url_for
from pydantic import ValidationError
from werkzeug.wrappers import Response

from backend.app.database import get_engine
from backend.app.domain import ALLOWED_TRANSITIONS, WorkItemStatus
from backend.app.errors import AppError
from backend.app.models import ActivityRow, ProjectRow, TagRow, WorkItemWithTagsRow
from backend.app.schemas.projects import ProjectCreate, ProjectUpdate
from backend.app.schemas.tags import TagCreate
from backend.app.schemas.work_items import (
    PriorityMove,
    StatusTransition,
    WorkItemCreate,
    WorkItemListFilter,
    WorkItemUpdate,
)
from backend.app.services import github as github_service
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


@ui_blueprint.post("/ui/projects/<uuid:project_id>")
def update_project(project_id: UUID) -> tuple[str, int] | Response:
    """Update project details from the board settings form."""
    try:
        command: ProjectUpdate = ProjectUpdate.model_validate(request.form.to_dict())
        project_service.update_project(get_engine(), project_id, command)
    except (ValidationError, AppError) as error:
        return render_project_board(project_id, project_error=str(error)), 422
    return redirect(url_for("ui.project_board", project_id=project_id))


@ui_blueprint.post("/ui/projects/<uuid:project_id>/archive")
def archive_project(project_id: UUID) -> Response:
    """Archive a project after the browser confirmation."""
    project_service.archive_project(get_engine(), project_id)
    return redirect(url_for("ui.project_board", project_id=project_id))


@ui_blueprint.post("/ui/projects/<uuid:project_id>/restore")
def restore_project(project_id: UUID) -> Response:
    """Restore a project from its read-only archive."""
    project_service.restore_project(get_engine(), project_id)
    return redirect(url_for("ui.project_board", project_id=project_id))


@ui_blueprint.post("/ui/projects/<uuid:project_id>/tags")
def create_project_tag(project_id: UUID) -> tuple[str, int] | Response:
    """Create a custom project tag and return to the board."""
    try:
        command: TagCreate = TagCreate.model_validate(request.form.to_dict())
        tag_service.create_tag(get_engine(), project_id, command)
    except (ValidationError, AppError) as error:
        return render_project_board(project_id, tag_error=str(error)), 422
    return redirect(url_for("ui.project_board", project_id=project_id))


def render_project_board(
    project_id: UUID,
    *,
    tag_error: str | None = None,
    project_error: str | None = None,
    tab: str | None = None,
) -> str:
    """Render a board with its complete project tag vocabulary."""
    context = board_context(project_id)
    active_tab: str = tab or request.args.get("tab", "board")
    if active_tab not in {"board", "activity", "repository"}:
        active_tab = "board"
    activity: list[ActivityRow] = (
        project_service.list_project_activity(get_engine(), project_id)
        if active_tab == "activity"
        else []
    )
    return render_template(
        "board.html",
        **context,
        active_tab=active_tab,
        tag_error=tag_error,
        project_error=project_error,
        activity=activity,
        repositories=(
            github_service.project_repositories(
                get_engine(), project_id, current_app.extensions["github_client"]
            )
            if active_tab == "repository"
            else []
        ),
    )


@ui_blueprint.post("/ui/projects/<uuid:project_id>/work-items")
def create_work_item(project_id: UUID) -> tuple[str, int] | Response:
    """Create a card and return a refreshed board fragment."""
    try:
        command: WorkItemCreate = WorkItemCreate.model_validate(form_with_tag_ids())
        work_item_service.create_work_item(get_engine(), project_id, command)
    except (ValidationError, AppError) as error:
        response: Response = make_response(
            render_template("partials/form_error.html", message=str(error)), 422
        )
        response.headers["HX-Retarget"] = "#story-create-error"
        response.headers["HX-Reswap"] = "innerHTML"
        return response
    return render_board_fragment(project_id), 201


@ui_blueprint.post("/ui/work-items/<uuid:work_item_id>/transitions")
def transition_work_item(work_item_id: UUID) -> tuple[str, int]:
    """Transition a card and return a refreshed board fragment."""
    command: StatusTransition = StatusTransition.model_validate(request.form.to_dict())
    item: WorkItemWithTagsRow = work_item_service.transition_work_item(
        get_engine(), work_item_id, command
    )
    return render_board_fragment(UUID(str(item["project_id"]))), 200


@ui_blueprint.post("/ui/work-items/<uuid:work_item_id>/priority")
def move_work_item_priority(work_item_id: UUID) -> tuple[str, int]:
    """Move a card within the current workflow lane and refresh the board."""
    command: PriorityMove = PriorityMove.model_validate(request.form.to_dict())
    item: WorkItemWithTagsRow = work_item_service.move_work_item_priority(
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
    return render_template("partials/board_columns.html", **board_context(project_id))


def board_context(project_id: UUID) -> dict[str, Any]:
    """Build the same filtered presentation data for pages and HTMX swaps."""
    project: ProjectRow = project_service.get_project(get_engine(), project_id, html=True)
    filters: WorkItemListFilter = WorkItemListFilter.model_validate(
        {
            "search": request.args.get("search"),
            "sort": request.args.get("sort", "priority"),
            "direction": request.args.get("direction", "asc"),
        }
    )
    items: list[WorkItemWithTagsRow] = work_item_service.list_work_items(
        get_engine(),
        project_id,
        search=filters.search,
        sort=filters.sort,
        direction=filters.direction,
    )
    project_tags: list[TagRow] = tag_service.list_project_tags(get_engine(), project_id)
    return {
        "project": project,
        "project_id": project_id,
        "project_archived": project["archived_at"] is not None,
        "grouped_items": group_work_items(items),
        "project_tags": project_tags,
        "filters": filters,
        "board_query": {
            "search": filters.search or "",
            "sort": filters.sort,
            "direction": filters.direction,
        },
        "statuses": list(WorkItemStatus),
        "allowed_transitions": ALLOWED_TRANSITIONS,
    }


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
    if "acceptance_criteria" in payload:
        payload["acceptance_criteria"] = [
            criterion.strip()
            for criterion in str(payload["acceptance_criteria"]).splitlines()
            if criterion.strip()
        ]
    return payload


@ui_blueprint.post("/ui/projects/<uuid:project_id>/repositories")
def update_project_repositories(project_id: UUID) -> tuple[str, int] | Response:
    """Save repository associations through the same project update use case."""
    try:
        urls = [
            line.strip()
            for line in request.form.get("repository_urls", "").splitlines()
            if line.strip()
        ]
        command = ProjectUpdate(repository_urls=urls)
        project_service.update_project(get_engine(), project_id, command)
    except (ValidationError, AppError) as error:
        return render_project_board(project_id, project_error=str(error), tab="repository"), 422
    return redirect(url_for("ui.project_board", project_id=project_id, tab="repository"))

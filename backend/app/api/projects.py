"""Project JSON endpoints."""

from uuid import UUID

from flask import Blueprint, Response, request

from backend.app.api.utils import json_model, json_models, parse_json
from backend.app.database import get_engine
from backend.app.models import ActivityRow, ProjectRow, TagRow, WorkItemWithTagsRow
from backend.app.schemas.common import ActivityEventRead
from backend.app.schemas.projects import ProjectCreate, ProjectRead
from backend.app.schemas.tags import TagCreate, TagFilter, TagRead
from backend.app.schemas.work_items import WorkItemCreate, WorkItemRead
from backend.app.services import projects as project_service
from backend.app.services import tags as tag_service
from backend.app.services import work_items as work_item_service

projects_blueprint: Blueprint = Blueprint("api_projects", __name__, url_prefix="/api/v1")


@projects_blueprint.post("/projects")
def create_project() -> tuple[Response, int]:
    """Create a project."""
    command: ProjectCreate = parse_json(ProjectCreate)
    project: ProjectRow = project_service.create_project(get_engine(), command)
    return json_model(ProjectRead.model_validate(project), status=201)


@projects_blueprint.get("/projects")
def list_projects() -> Response:
    """List projects."""
    projects: list[ProjectRow] = project_service.list_projects(get_engine())
    return json_models([ProjectRead.model_validate(project) for project in projects])


@projects_blueprint.get("/projects/<uuid:project_id>")
def get_project(project_id: UUID) -> tuple[Response, int]:
    """Get a project."""
    project: ProjectRow = project_service.get_project(get_engine(), project_id)
    return json_model(ProjectRead.model_validate(project))


@projects_blueprint.post("/projects/<uuid:project_id>/tags")
def create_project_tag(project_id: UUID) -> tuple[Response, int]:
    """Create a custom tag within a project."""
    command: TagCreate = parse_json(TagCreate)
    tag: TagRow = tag_service.create_tag(get_engine(), project_id, command)
    return json_model(TagRead.model_validate(tag), status=201)


@projects_blueprint.get("/projects/<uuid:project_id>/tags")
def list_project_tags(project_id: UUID) -> Response:
    """List the tags available to a project."""
    tags: list[TagRow] = tag_service.list_project_tags(get_engine(), project_id)
    return json_models([TagRead.model_validate(tag) for tag in tags])


@projects_blueprint.post("/projects/<uuid:project_id>/work-items")
def create_project_work_item(project_id: UUID) -> tuple[Response, int]:
    """Create a work item within a project."""
    command: WorkItemCreate = parse_json(WorkItemCreate)
    item: WorkItemWithTagsRow = work_item_service.create_work_item(
        get_engine(), project_id, command
    )
    return json_model(WorkItemRead.model_validate(item), status=201)


@projects_blueprint.get("/projects/<uuid:project_id>/work-items")
def list_project_work_items(project_id: UUID) -> Response:
    """List a project's work items."""
    filters: TagFilter = TagFilter.model_validate({"tag_ids": request.args.getlist("tag_id")})
    items: list[WorkItemWithTagsRow] = work_item_service.list_work_items(
        get_engine(), project_id, filter_tag_ids=filters.tag_ids
    )
    return json_models([WorkItemRead.model_validate(item) for item in items])


@projects_blueprint.get("/projects/<uuid:project_id>/activity")
def list_project_activity(project_id: UUID) -> Response:
    """List recent immutable activity events for a project."""
    events: list[ActivityRow] = project_service.list_project_activity(get_engine(), project_id)
    return json_models([ActivityEventRead.model_validate(event) for event in events])

"""Project JSON endpoints."""

from uuid import UUID

from flask import Blueprint, Response, request

from backend.app.api.idempotency import execute_idempotent
from backend.app.api.utils import json_model, json_models, parse_if_match, parse_json
from backend.app.database import get_engine
from backend.app.models import ActivityRow, ProjectRow, TagRow, WorkItemWithTagsRow
from backend.app.schemas.common import ActivityEventRead
from backend.app.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from backend.app.schemas.tags import TagCreate, TagRead
from backend.app.schemas.work_items import WorkItemCreate, WorkItemListFilter, WorkItemRead
from backend.app.services import projects as project_service
from backend.app.services import tags as tag_service
from backend.app.services import work_items as work_item_service

projects_blueprint: Blueprint = Blueprint("api_projects", __name__, url_prefix="/api/v1")


@projects_blueprint.post("/projects")
def create_project() -> tuple[Response, int]:
    """Create a project."""
    command: ProjectCreate = parse_json(ProjectCreate)
    project, status = execute_idempotent(
        get_engine(),
        scope="POST:/api/v1/projects",
        command=command,
        expected_version=None,
        model_type=ProjectRead,
        status=201,
        operation=lambda: ProjectRead.model_validate(
            project_service.create_project(get_engine(), command)
        ),
    )
    return json_model(project, status=status, etag=project.version)


@projects_blueprint.get("/projects")
def list_projects() -> Response:
    """List projects."""
    projects: list[ProjectRow] = project_service.list_projects(get_engine())
    return json_models([ProjectRead.model_validate(project) for project in projects])


@projects_blueprint.get("/projects/<uuid:project_id>")
def get_project(project_id: UUID) -> tuple[Response, int]:
    """Get a project."""
    project: ProjectRow = project_service.get_project(get_engine(), project_id)
    return json_model(ProjectRead.model_validate(project), etag=project["version"])


@projects_blueprint.patch("/projects/<uuid:project_id>")
def update_project(project_id: UUID) -> tuple[Response, int]:
    """Edit an active project's name or description."""
    command: ProjectUpdate = parse_json(ProjectUpdate)
    expected_version: int | None = parse_if_match()
    project, status = execute_idempotent(
        get_engine(),
        scope=f"PATCH:/api/v1/projects/{project_id}",
        command=command,
        expected_version=expected_version,
        model_type=ProjectRead,
        status=200,
        operation=lambda: ProjectRead.model_validate(
            project_service.update_project(
                get_engine(), project_id, command, expected_version=expected_version
            )
        ),
    )
    return json_model(project, status=status, etag=project.version)


@projects_blueprint.post("/projects/<uuid:project_id>/archive")
def archive_project(project_id: UUID) -> tuple[Response, int]:
    """Archive a project without deleting its history."""
    expected_version: int | None = parse_if_match()
    project, status = execute_idempotent(
        get_engine(),
        scope=f"POST:/api/v1/projects/{project_id}/archive",
        command=ProjectUpdate.model_construct(),
        expected_version=expected_version,
        model_type=ProjectRead,
        status=200,
        operation=lambda: ProjectRead.model_validate(
            project_service.archive_project(
                get_engine(), project_id, expected_version=expected_version
            )
        ),
    )
    return json_model(project, status=status, etag=project.version)


@projects_blueprint.post("/projects/<uuid:project_id>/restore")
def restore_project(project_id: UUID) -> tuple[Response, int]:
    """Restore an archived project."""
    expected_version: int | None = parse_if_match()
    project, status = execute_idempotent(
        get_engine(),
        scope=f"POST:/api/v1/projects/{project_id}/restore",
        command=ProjectUpdate.model_construct(),
        expected_version=expected_version,
        model_type=ProjectRead,
        status=200,
        operation=lambda: ProjectRead.model_validate(
            project_service.restore_project(
                get_engine(), project_id, expected_version=expected_version
            )
        ),
    )
    return json_model(project, status=status, etag=project.version)


@projects_blueprint.post("/projects/<uuid:project_id>/tags")
def create_project_tag(project_id: UUID) -> tuple[Response, int]:
    """Create a custom tag within a project."""
    command: TagCreate = parse_json(TagCreate)
    tag, status = execute_idempotent(
        get_engine(),
        scope=f"POST:/api/v1/projects/{project_id}/tags",
        command=command,
        expected_version=None,
        model_type=TagRead,
        status=201,
        operation=lambda: TagRead.model_validate(
            tag_service.create_tag(get_engine(), project_id, command)
        ),
    )
    return json_model(tag, status=status)


@projects_blueprint.get("/projects/<uuid:project_id>/tags")
def list_project_tags(project_id: UUID) -> Response:
    """List the tags available to a project."""
    tags: list[TagRow] = tag_service.list_project_tags(get_engine(), project_id)
    return json_models([TagRead.model_validate(tag) for tag in tags])


@projects_blueprint.post("/projects/<uuid:project_id>/work-items")
def create_project_work_item(project_id: UUID) -> tuple[Response, int]:
    """Create a work item within a project."""
    command: WorkItemCreate = parse_json(WorkItemCreate)
    item, status = execute_idempotent(
        get_engine(),
        scope=f"POST:/api/v1/projects/{project_id}/work-items",
        command=command,
        expected_version=None,
        model_type=WorkItemRead,
        status=201,
        operation=lambda: WorkItemRead.model_validate(
            work_item_service.create_work_item(get_engine(), project_id, command)
        ),
    )
    return json_model(item, status=status, etag=item.version)


@projects_blueprint.get("/projects/<uuid:project_id>/work-items")
def list_project_work_items(project_id: UUID) -> Response:
    """List a project's work items."""
    filters: WorkItemListFilter = WorkItemListFilter.model_validate(
        {
            "tag_ids": request.args.getlist("tag_id"),
            "search": request.args.get("search"),
            "sort": request.args.get("sort", "priority"),
            "direction": request.args.get("direction", "asc"),
            "limit": request.args.get("limit"),
            "cursor": request.args.get("cursor"),
        }
    )
    if filters.limit is not None:
        page = work_item_service.list_work_items_page(
            get_engine(),
            project_id,
            filter_tag_ids=filters.tag_ids,
            search=filters.search,
            sort=filters.sort,
            direction=filters.direction,
            limit=filters.limit,
            cursor=filters.cursor,
        )
        return json_models(
            [WorkItemRead.model_validate(item) for item in page["items"]],
            next_cursor=page["next_cursor"],
            include_page_meta=True,
        )
    items: list[WorkItemWithTagsRow] = work_item_service.list_work_items(
        get_engine(),
        project_id,
        filter_tag_ids=filters.tag_ids,
        search=filters.search,
        sort=filters.sort,
        direction=filters.direction,
    )
    return json_models([WorkItemRead.model_validate(item) for item in items])


@projects_blueprint.get("/projects/<uuid:project_id>/activity")
def list_project_activity(project_id: UUID) -> Response:
    """List recent immutable activity events for a project."""
    events: list[ActivityRow] = project_service.list_project_activity(get_engine(), project_id)
    return json_models([ActivityEventRead.model_validate(event) for event in events])

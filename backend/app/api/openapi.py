"""Generated OpenAPI document for the public versioned JSON API."""

from typing import Any

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel

from backend.app.schemas.common import ActivityEventRead
from backend.app.schemas.github import GitHubRepository
from backend.app.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from backend.app.schemas.tags import TagCreate, TagRead
from backend.app.schemas.work_items import (
    PriorityMove,
    StatusTransition,
    WorkItemCreate,
    WorkItemRead,
    WorkItemUpdate,
)

openapi_blueprint: Blueprint = Blueprint("api_openapi", __name__, url_prefix="/api/v1")


def schema_reference(model: type[BaseModel]) -> dict[str, str]:
    """Return a component reference for one Pydantic schema."""
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def request_body(model: type[BaseModel]) -> dict[str, Any]:
    """Build a JSON request body from a Pydantic command schema."""
    return {
        "required": True,
        "content": {"application/json": {"schema": schema_reference(model)}},
    }


def data_response(model: type[BaseModel], status: str, description: str) -> dict[str, Any]:
    """Build the standard single-resource response envelope."""
    return {
        status: {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["data"],
                        "properties": {"data": schema_reference(model)},
                    }
                }
            },
        }
    }


def data_collection_response(model: type[BaseModel], description: str) -> dict[str, Any]:
    """Build the standard collection response envelope."""
    return {
        "200": {
            "description": description,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["data"],
                        "properties": {"data": {"type": "array", "items": schema_reference(model)}},
                    }
                }
            },
        }
    }


def uuid_parameter(name: str) -> dict[str, Any]:
    """Describe a UUID path parameter shared by public routes."""
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": "string", "format": "uuid"},
    }


def write_safety_parameters(*, conditional: bool) -> list[dict[str, Any]]:
    """Describe the replay and optimistic-concurrency headers accepted by writes."""
    parameters: list[dict[str, Any]] = [
        {
            "name": "Idempotency-Key",
            "in": "header",
            "description": "Optional unique key that safely replays the same write response.",
            "schema": {"type": "string", "minLength": 1, "maxLength": 255},
        }
    ]
    if conditional:
        parameters.append(
            {
                "name": "If-Match",
                "in": "header",
                "description": "Optional quoted ETag from the current project or story response.",
                "schema": {"type": "string"},
            }
        )
    return parameters


def work_item_list_parameters() -> list[dict[str, Any]]:
    """Describe story collection filters and the opt-in cursor traversal contract."""
    return [
        {
            "name": "tag_id",
            "in": "query",
            "description": "Repeat to match stories with any selected project tag.",
            "style": "form",
            "explode": True,
            "schema": {
                "type": "array",
                "items": {"type": "string", "format": "uuid"},
                "maxItems": 20,
            },
        },
        {
            "name": "search",
            "in": "query",
            "schema": {"type": "string", "maxLength": 200},
        },
        {
            "name": "sort",
            "in": "query",
            "schema": {
                "type": "string",
                "enum": ["priority", "created_at", "updated_at", "title", "status"],
                "default": "priority",
            },
        },
        {
            "name": "direction",
            "in": "query",
            "schema": {"type": "string", "enum": ["asc", "desc"], "default": "asc"},
        },
        {
            "name": "limit",
            "in": "query",
            "description": "Opt into cursor pagination with 1 to 100 stories per response.",
            "schema": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        {
            "name": "cursor",
            "in": "query",
            "description": "Opaque continuation token from meta.next_cursor; requires limit.",
            "schema": {"type": "string", "maxLength": 2048},
        },
    ]


def generated_components(models: tuple[type[BaseModel], ...]) -> dict[str, Any]:
    """Generate reusable OpenAPI components, including Pydantic nested definitions."""
    components: dict[str, Any] = {}
    for model in models:
        schema: dict[str, Any] = model.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        definitions: dict[str, Any] = schema.pop("$defs", {})
        for name, definition in definitions.items():
            components.setdefault(name, definition)
        components[model.__name__] = schema
    return components


def openapi_document() -> dict[str, Any]:
    """Generate the OpenAPI 3.1 document from the public command and read schemas."""
    schemas: tuple[type[BaseModel], ...] = (
        ActivityEventRead,
        GitHubRepository,
        PriorityMove,
        ProjectCreate,
        ProjectRead,
        ProjectUpdate,
        StatusTransition,
        TagCreate,
        TagRead,
        WorkItemCreate,
        WorkItemRead,
        WorkItemUpdate,
    )
    project_id: dict[str, Any] = uuid_parameter("project_id")
    work_item_id: dict[str, Any] = uuid_parameter("work_item_id")
    document: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Solar Forge Boards API",
            "version": "1.0.0",
            "description": "The versioned JSON contract for Solar Forge Boards clients and agents.",
        },
        "paths": {
            "/api/v1/projects": {
                "get": {"responses": data_collection_response(ProjectRead, "Projects")},
                "post": {
                    "parameters": write_safety_parameters(conditional=False),
                    "requestBody": request_body(ProjectCreate),
                    "responses": data_response(ProjectRead, "201", "Project created"),
                },
            },
            "/api/v1/projects/{project_id}": {
                "parameters": [project_id],
                "get": {"responses": data_response(ProjectRead, "200", "Project")},
                "patch": {
                    "parameters": write_safety_parameters(conditional=True),
                    "requestBody": request_body(ProjectUpdate),
                    "responses": data_response(ProjectRead, "200", "Project updated"),
                },
            },
            "/api/v1/projects/{project_id}/archive": {
                "parameters": [project_id],
                "post": {
                    "parameters": write_safety_parameters(conditional=True),
                    "responses": data_response(ProjectRead, "200", "Project archived"),
                },
            },
            "/api/v1/projects/{project_id}/restore": {
                "parameters": [project_id],
                "post": {
                    "parameters": write_safety_parameters(conditional=True),
                    "responses": data_response(ProjectRead, "200", "Project restored"),
                },
            },
            "/api/v1/projects/{project_id}/tags": {
                "parameters": [project_id],
                "get": {"responses": data_collection_response(TagRead, "Project tags")},
                "post": {
                    "parameters": write_safety_parameters(conditional=False),
                    "requestBody": request_body(TagCreate),
                    "responses": data_response(TagRead, "201", "Tag created"),
                },
            },
            "/api/v1/projects/{project_id}/work-items": {
                "parameters": [project_id, *work_item_list_parameters()],
                "get": {"responses": data_collection_response(WorkItemRead, "Project stories")},
                "post": {
                    "parameters": write_safety_parameters(conditional=False),
                    "requestBody": request_body(WorkItemCreate),
                    "responses": data_response(WorkItemRead, "201", "Story created"),
                },
            },
            "/api/v1/projects/{project_id}/repositories": {
                "parameters": [project_id],
                "get": {
                    "responses": data_collection_response(GitHubRepository, "GitHub repositories")
                },
            },
            "/api/v1/projects/{project_id}/activity": {
                "parameters": [project_id],
                "get": {
                    "responses": data_collection_response(ActivityEventRead, "Project activity")
                },
            },
            "/api/v1/work-items/by-reference/{reference_number}": {
                "parameters": [
                    {
                        "name": "reference_number",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer", "minimum": 1},
                    }
                ],
                "get": {"responses": data_response(WorkItemRead, "200", "Story")},
            },
            "/api/v1/work-items/{work_item_id}": {
                "parameters": [work_item_id],
                "get": {"responses": data_response(WorkItemRead, "200", "Story")},
                "patch": {
                    "parameters": write_safety_parameters(conditional=True),
                    "requestBody": request_body(WorkItemUpdate),
                    "responses": data_response(WorkItemRead, "200", "Story updated"),
                },
                "delete": {"responses": {"204": {"description": "Story deleted"}}},
            },
            "/api/v1/work-items/{work_item_id}/transitions": {
                "parameters": [work_item_id],
                "post": {
                    "parameters": write_safety_parameters(conditional=True),
                    "requestBody": request_body(StatusTransition),
                    "responses": data_response(WorkItemRead, "200", "Story transitioned"),
                },
            },
            "/api/v1/work-items/{work_item_id}/priority": {
                "parameters": [work_item_id],
                "post": {
                    "parameters": write_safety_parameters(conditional=True),
                    "requestBody": request_body(PriorityMove),
                    "responses": data_response(WorkItemRead, "200", "Story reprioritized"),
                },
            },
        },
        "components": {"schemas": generated_components(schemas)},
    }
    for path in document["paths"].values():
        path.setdefault("parameters", []).append(
            {
                "name": "X-Correlation-ID",
                "in": "header",
                "description": "Trace generated when omitted and echoed on responses.",
                "schema": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"},
            }
        )
        for method in ("get", "post", "patch", "delete"):
            if method in path:
                for response in path[method]["responses"].values():
                    response.setdefault("headers", {})["X-Correlation-ID"] = {
                        "schema": {"type": "string"},
                        "description": "Request trace, also returned on errors.",
                    }
    return document


@openapi_blueprint.get("/openapi.json")
def get_openapi_document() -> Response:
    """Publish the generated versioned API contract."""
    return jsonify(openapi_document())

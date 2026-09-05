"""Discoverable, narrowly scoped tools with approval owned by the trusted host."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

from pydantic import Field, ValidationError, create_model

from backend.app.agent.transport import Transport
from backend.app.correlation import valid_correlation_id
from backend.app.schemas.common import ApiModel
from backend.app.schemas.projects import ProjectCreate, ProjectUpdate
from backend.app.schemas.tags import TagCreate
from backend.app.schemas.work_items import (
    StatusTransition,
    WorkItemCreate,
    WorkItemListFilter,
    WorkItemUpdate,
)


@dataclass(frozen=True)
class Tool:
    """One fixed public endpoint and its model-visible argument contract."""

    name: str
    description: str
    method: str
    path: str
    scope: str
    arguments: type[ApiModel]


def arguments(
    name: str,
    *,
    resource: str | None = None,
    command: type[ApiModel] | None = None,
    filters: bool = False,
    reference: bool = False,
) -> type[ApiModel]:
    """Compose transport arguments from existing API schemas."""
    fields: dict[str, Any] = {}
    if resource:
        fields[resource] = (UUID, ...)
    if command:
        fields["command"] = (command, ...)
    if filters:
        fields["filters"] = (WorkItemListFilter, Field(default_factory=WorkItemListFilter))
    if reference:
        fields["reference_number"] = (int, Field(gt=0))
    return create_model(name, __base__=ApiModel, **fields)


TOOLS: tuple[Tool, ...] = (
    Tool(
        "list_projects",
        "List projects.",
        "GET",
        "/projects",
        "projects:read",
        arguments("ListProjects"),
    ),
    Tool(
        "get_project",
        "Read project context.",
        "GET",
        "/projects/{project_id}",
        "projects:read",
        arguments("GetProject", resource="project_id"),
    ),
    Tool(
        "list_tags",
        "Resolve the project's tag vocabulary.",
        "GET",
        "/projects/{project_id}/tags",
        "tags:read",
        arguments("ListTags", resource="project_id"),
    ),
    Tool(
        "list_stories",
        "List stories; follow next_cursor using identical filters.",
        "GET",
        "/projects/{project_id}/work-items",
        "work_items:read",
        arguments("ListStories", resource="project_id", filters=True),
    ),
    Tool(
        "get_story",
        "Read a story with complete tags.",
        "GET",
        "/work-items/{work_item_id}",
        "work_items:read",
        arguments("GetStory", resource="work_item_id"),
    ),
    Tool(
        "get_story_by_reference",
        "Resolve a visible story number.",
        "GET",
        "/work-items/by-reference/{reference_number}",
        "work_items:read",
        arguments("GetStoryByReference", reference=True),
    ),
    Tool(
        "list_activity",
        "Read the newest 50 project events.",
        "GET",
        "/projects/{project_id}/activity",
        "activity:read",
        arguments("ListActivity", resource="project_id"),
    ),
    Tool(
        "create_project",
        "Create a project and its default tags after host approval.",
        "POST",
        "/projects",
        "projects:write",
        arguments("CreateProject", command=ProjectCreate),
    ),
    Tool(
        "update_project",
        "Update project content after host approval.",
        "PATCH",
        "/projects/{project_id}",
        "projects:write",
        arguments("UpdateProject", resource="project_id", command=ProjectUpdate),
    ),
    Tool(
        "create_story",
        "Create a Todo story after host approval.",
        "POST",
        "/projects/{project_id}/work-items",
        "work_items:write",
        arguments("CreateStory", resource="project_id", command=WorkItemCreate),
    ),
    Tool(
        "update_story",
        "Update story content after host approval; status is separate.",
        "PATCH",
        "/work-items/{work_item_id}",
        "work_items:write",
        arguments("UpdateStory", resource="work_item_id", command=WorkItemUpdate),
    ),
    Tool(
        "transition_story",
        "Request a valid status transition after host approval.",
        "POST",
        "/work-items/{work_item_id}/transitions",
        "work_items:transition",
        arguments("TransitionStory", resource="work_item_id", command=StatusTransition),
    ),
    Tool(
        "create_tag",
        "Extend tag vocabulary; requires human confirmation for this exact call.",
        "POST",
        "/projects/{project_id}/tags",
        "tags:write",
        arguments("CreateTag", resource="project_id", command=TagCreate),
    ),
    Tool(
        "delete_story",
        "Permanently delete a story; requires human confirmation for this exact call.",
        "DELETE",
        "/work-items/{work_item_id}",
        "work_items:delete",
        arguments("DeleteStory", resource="work_item_id"),
    ),
)
READ_SCOPES = frozenset({"projects:read", "tags:read", "work_items:read", "activity:read"})
Approval = Callable[[str, dict[str, Any]], bool]


class SolarForgeTools:
    """Expose only host-granted capabilities; approval is never a model argument."""

    def __init__(
        self,
        transport: Transport,
        *,
        scopes: frozenset[str] = READ_SCOPES,
        approve_write: Approval | None = None,
        confirm_human: Approval | None = None,
    ) -> None:
        self.transport = transport
        self.scopes = frozenset(scopes)
        self.approve_write = approve_write
        self.confirm_human = confirm_human

    def definitions(self) -> list[dict[str, Any]]:
        """Return framework-neutral function definitions for the permitted tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.arguments.model_json_schema(),
            }
            for tool in TOOLS
            if tool.scope in self.scopes
        ]

    def call(
        self,
        name: str,
        supplied: dict[str, Any],
        *,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        etag: str | None = None,
    ) -> dict[str, Any]:
        """Execute a model proposal with metadata supplied separately by its trusted host."""
        trace = correlation_id if correlation_id is not None else str(uuid4())
        if not valid_correlation_id(trace):
            return {"error": {"code": "invalid_correlation_id"}}
        metadata: dict[str, Any] = {"correlation_id": trace}

        def failure(code: str) -> dict[str, Any]:
            return {"error": {"code": code}, "meta": metadata}

        tool = next((item for item in TOOLS if item.name == name), None)
        if tool is None:
            return failure("unknown_tool")
        if tool.scope not in self.scopes:
            return failure("scope_denied")
        try:
            parsed = tool.arguments.model_validate(supplied)
        except ValidationError as error:
            return {
                "error": {
                    "code": "validation_error",
                    "details": error.errors(
                        include_url=False, include_context=False, include_input=False
                    ),
                },
                "meta": metadata,
            }
        values = parsed.model_dump(mode="json", exclude_unset=True)
        write = tool.method != "GET"
        if write:
            approval = (
                self.confirm_human if name in {"delete_story", "create_tag"} else self.approve_write
            )
            if approval is None or not approval(name, deepcopy(values)):
                return failure("approval_required")
        path = "/api/v1" + tool.path.format(**values)
        if "filters" in values:
            query = values["filters"]
            query["tag_id"] = query.pop("tag_ids", [])
            path += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
        headers = {"X-Correlation-ID": trace}
        if write and tool.method != "DELETE":
            key = idempotency_key or str(uuid4())
            headers["Idempotency-Key"] = key
            metadata["idempotency_key"] = key
        if etag is not None:
            headers["If-Match"] = etag
        response = self.transport.request(tool.method, path, values.get("command"), headers)
        metadata.update(
            {
                "status": response.status,
                "correlation_id": response.headers.get("x-correlation-id", trace),
            }
        )
        if "etag" in response.headers:
            metadata["etag"] = response.headers["etag"]
        return {**response.body, "meta": {**response.body.get("meta", {}), **metadata}}

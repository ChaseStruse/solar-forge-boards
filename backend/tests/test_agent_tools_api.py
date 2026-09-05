"""Exercise model tools against the public API and isolated database."""

from collections.abc import Iterator
from threading import Thread
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.serving import make_server

from backend.app.agent import HttpTransport, SolarForgeTools
from backend.app.agent.tools import READ_SCOPES, TOOLS
from backend.app.agent.transport import ApiResponse
from backend.app.correlation import correlation_id


class ClientTransport:
    """Connect tool dispatch to the real Flask routes without development data."""

    def __init__(self, client: FlaskClient) -> None:
        self.client = client
        self.calls = 0

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None, headers: dict[str, str]
    ) -> ApiResponse:
        self.calls += 1
        response = self.client.open(path, method=method, json=payload, headers=headers)
        return ApiResponse(
            response.status_code,
            response.get_json() if response.data else {},
            {key.lower(): value for key, value in response.headers.items()},
        )


def approve(name: str, proposal: dict[str, Any]) -> bool:
    """Simulate a trusted host's explicit approval."""
    return True


@pytest.fixture
def agent(client: FlaskClient) -> SolarForgeTools:
    return SolarForgeTools(
        ClientTransport(client),
        scopes=frozenset(tool.scope for tool in TOOLS),
        approve_write=approve,
        confirm_human=approve,
    )


def test_agent_read_create_update_transition_and_trace(agent: SolarForgeTools) -> None:
    project = agent.call("create_project", {"command": {"name": "Tools"}}, correlation_id="plan-6")
    project_id = project["data"]["id"]
    assert agent.call("list_projects", {})["data"][0]["id"] == project_id
    assert agent.call("get_project", {"project_id": project_id})["data"]["name"] == "Tools"
    tags = agent.call("list_tags", {"project_id": project_id})["data"]
    assert len(tags) == 4
    story = agent.call(
        "create_story",
        {
            "project_id": project_id,
            "command": {
                "title": "Agent story",
                "tag_ids": [tags[0]["id"]],
            },
        },
        correlation_id="plan-6",
        idempotency_key="create-story",
    )
    story_id = story["data"]["id"]
    assert story["data"]["tags"][0] == tags[0]
    replay = agent.call(
        "create_story",
        {
            "project_id": project_id,
            "command": {
                "title": "Agent story",
                "tag_ids": [tags[0]["id"]],
            },
        },
        correlation_id="retry-6",
        idempotency_key="create-story",
    )
    assert replay["data"] == story["data"]
    assert replay["meta"]["correlation_id"] == "retry-6"
    assert agent.call("get_story", {"work_item_id": story_id})["data"] == story["data"]
    assert (
        agent.call(
            "get_story_by_reference",
            {
                "reference_number": story["data"]["reference_number"],
            },
        )["data"]
        == story["data"]
    )
    updated = agent.call(
        "update_story",
        {
            "work_item_id": story_id,
            "command": {
                "title": "Updated",
                "description": "context",
            },
        },
        etag=story["meta"]["etag"],
        correlation_id="plan-6",
    )
    assert updated["data"]["title"] == "Updated"
    stale = agent.call(
        "update_story",
        {
            "work_item_id": story_id,
            "command": {
                "title": "Stale",
            },
        },
        etag=story["meta"]["etag"],
    )
    assert stale["error"]["code"] == "version_conflict"
    assert stale["meta"]["status"] == 409
    moved = agent.call(
        "transition_story",
        {
            "work_item_id": story_id,
            "command": {
                "status": "done",
            },
        },
        correlation_id="plan-6",
    )
    assert moved["data"]["status"] == "done"
    invalid = agent.call(
        "transition_story",
        {
            "work_item_id": story_id,
            "command": {
                "status": "todo",
            },
        },
        correlation_id="invalid-transition",
    )
    assert invalid["error"]["code"] == "invalid_status_transition"
    assert invalid["meta"]["correlation_id"] == "invalid-transition"
    page = agent.call(
        "list_stories",
        {
            "project_id": project_id,
            "filters": {
                "search": "context",
                "tag_ids": [tags[0]["id"]],
                "limit": 1,
            },
        },
    )
    assert page["data"][0]["id"] == story_id
    assert page["meta"]["next_cursor"] is None
    events = agent.call("list_activity", {"project_id": project_id})["data"]
    assert len(events) == 4
    assert {event["details"]["correlation_id"] for event in events} == {"plan-6"}


def test_default_scopes_and_host_approval(client: FlaskClient, work_item_id: str) -> None:
    transport = ClientTransport(client)
    reader = SolarForgeTools(transport)
    assert all(
        tool["name"] not in {"delete_story", "create_tag", "create_story"}
        for tool in reader.definitions()
    )
    assert (
        reader.call("delete_story", {"work_item_id": work_item_id})["error"]["code"]
        == "scope_denied"
    )
    writer = SolarForgeTools(transport, scopes=READ_SCOPES | {"work_items:write"})
    assert (
        writer.call(
            "update_story",
            {
                "work_item_id": work_item_id,
                "command": {
                    "title": "Proposal",
                },
            },
        )["error"]["code"]
        == "approval_required"
    )
    assert (
        writer.call(
            "update_story",
            {"work_item_id": work_item_id, "approved": True, "command": {"title": "Bypass"}},
        )["error"]["code"]
        == "validation_error"
    )
    assert transport.calls == 0


def test_high_impact_requires_separate_human_confirmation(
    client: FlaskClient,
    project_id: str,
    work_item_id: str,
) -> None:
    transport = ClientTransport(client)
    tools = SolarForgeTools(
        transport, scopes=frozenset({"work_items:delete", "tags:write"}), approve_write=approve
    )
    proposals: list[tuple[str, dict[str, Any]]] = [
        ("delete_story", {"work_item_id": work_item_id}),
        ("create_tag", {"project_id": project_id, "command": {"name": "New"}}),
    ]
    for name, args in proposals:
        assert tools.call(name, args)["error"]["code"] == "approval_required"
    assert transport.calls == 0
    tools.confirm_human = approve
    assert (
        tools.call("create_tag", {"project_id": project_id, "command": {"name": "New"}})["meta"][
            "status"
        ]
        == 201
    )
    assert tools.call("delete_story", {"work_item_id": work_item_id})["meta"]["status"] == 204


def test_correlation_errors_and_context_cleanup(client: FlaskClient, project_id: str) -> None:
    response = client.post("/api/v1/projects", json={}, headers={"X-Correlation-ID": "validation"})
    assert response.status_code == 422
    assert response.headers["X-Correlation-ID"] == "validation"
    assert correlation_id.get() is None
    bad = client.get("/api/v1/projects", headers={"X-Correlation-ID": "bad trace"})
    assert bad.status_code == 422
    assert bad.json is not None and bad.json["error"]["code"] == "invalid_correlation_id"
    assert bad.headers["X-Correlation-ID"] != "bad trace"
    missing = client.get("/api/v1/missing", headers={"X-Correlation-ID": "missing"})
    assert missing.status_code == 404
    assert missing.headers["X-Correlation-ID"] == "missing"
    generated = client.get(f"/api/v1/projects/{project_id}")
    assert generated.headers["X-Correlation-ID"] not in {"validation", "missing"}
    assert correlation_id.get() is None


@pytest.fixture
def http_origin(app: Flask) -> Iterator[str]:
    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_real_http_transport(http_origin: str, project_id: str) -> None:
    tools = SolarForgeTools(HttpTransport(http_origin))
    assert tools.call("get_project", {"project_id": project_id})["data"]["id"] == project_id
    failure = tools.call(
        "get_story_by_reference", {"reference_number": 999}, correlation_id="http-6"
    )
    assert failure["error"]["code"] == "not_found"
    assert failure["meta"]["status"] == 404
    assert failure["meta"]["correlation_id"] == "http-6"


def test_tool_pagination_and_project_update(agent: SolarForgeTools, project_id: str) -> None:
    changed = agent.call(
        "update_project",
        {
            "project_id": project_id,
            "command": {
                "description": "Agent context",
            },
        },
    )
    assert changed["data"]["description"] == "Agent context"
    for title in ["First", "Second"]:
        agent.call("create_story", {"project_id": project_id, "command": {"title": title}})
    query: dict[str, Any] = {"sort": "title", "limit": 1}
    first = agent.call("list_stories", {"project_id": project_id, "filters": query})
    assert first["data"][0]["title"] == "First"
    query["cursor"] = first["meta"]["next_cursor"]
    second = agent.call("list_stories", {"project_id": project_id, "filters": query})
    assert second["data"][0]["title"] == "Second"
    assert second["meta"]["next_cursor"] is None


def test_tool_validation_and_schema(client: FlaskClient) -> None:
    transport = ClientTransport(client)
    tools = SolarForgeTools(transport)
    assert (
        tools.call("get_story", {"work_item_id": "../projects"})["error"]["code"]
        == "validation_error"
    )
    assert tools.call("unknown", {})["error"]["code"] == "unknown_tool"
    assert (
        tools.call("list_projects", {}, correlation_id="bad trace")["error"]["code"]
        == "invalid_correlation_id"
    )
    assert transport.calls == 0
    for definition in tools.definitions():
        assert definition["parameters"]["additionalProperties"] is False
        assert "approved" not in definition["parameters"]["properties"]
    contract = client.get("/api/v1/openapi.json").get_json()
    for path in contract["paths"].values():
        assert any(parameter["name"] == "X-Correlation-ID" for parameter in path["parameters"])

"""Project API behavior."""

import pytest
from flask.testing import FlaskClient


def test_create_list_and_get_project(client: FlaskClient) -> None:
    """A project moves through the public create/list/get API."""
    created = client.post(
        "/api/v1/projects",
        json={"name": "  Atlas  ", "description": "A clear plan"},
    )
    assert created.status_code == 201
    project: dict[str, str] = created.get_json()["data"]
    assert project["name"] == "Atlas"

    listed = client.get("/api/v1/projects")
    assert listed.status_code == 200
    assert listed.get_json()["data"] == [project]

    fetched = client.get(f"/api/v1/projects/{project['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["data"] == project


def test_project_name_is_unique(client: FlaskClient, project_id: str) -> None:
    """Duplicate names produce a stable conflict response."""
    del project_id
    response = client.post("/api/v1/projects", json={"name": "Solar Forge"})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "project_name_conflict"


def test_project_validation_error_is_structured(client: FlaskClient) -> None:
    """Invalid input is returned as a machine-readable error."""
    response = client.post("/api/v1/projects", json={"name": "   "})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"


def test_missing_project_returns_not_found(client: FlaskClient) -> None:
    """Unknown identifiers receive a 404 error envelope."""
    response = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_project_can_be_edited_archived_and_restored(client: FlaskClient, project_id: str) -> None:
    """Projects retain their history through a reversible, write-blocking archive state."""
    updated = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Solar Forge Core", "description": "Plan the foundation."},
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["name"] == "Solar Forge Core"

    archived = client.post(f"/api/v1/projects/{project_id}/archive")
    assert archived.status_code == 200
    assert archived.get_json()["data"]["archived_at"] is not None
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/work-items", json={"title": "Too late"}
        ).get_json()["error"]["code"]
        == "project_archived"
    )

    restored = client.post(f"/api/v1/projects/{project_id}/restore")
    assert restored.status_code == 200
    assert restored.get_json()["data"]["archived_at"] is None
    event_types = {
        event["event_type"]
        for event in client.get(f"/api/v1/projects/{project_id}/activity").get_json()["data"]
    }
    assert {"project.updated", "project.archived", "project.restored"} <= event_types


def test_project_conditional_write_rejects_a_stale_etag(
    client: FlaskClient, project_id: str
) -> None:
    """Agents can avoid overwriting a project revision they did not read."""
    fetched = client.get(f"/api/v1/projects/{project_id}")
    assert fetched.headers["ETag"] == '"1"'

    first = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"If-Match": fetched.headers["ETag"]},
        json={"description": "First editor wins."},
    )
    assert first.status_code == 200
    assert first.headers["ETag"] == '"2"'

    stale = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"If-Match": fetched.headers["ETag"]},
        json={"description": "Old editor must not overwrite."},
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "version_conflict"


@pytest.mark.parametrize("operation", ["update", "archive", "restore"])
def test_stale_noop_project_write_is_rejected(
    client: FlaskClient, project_id: str, operation: str
) -> None:
    """Project no-ops enforce revisions just like meaningful writes."""
    path = f"/api/v1/projects/{project_id}"
    client.patch(path, json={"name": "Current"})
    if operation == "archive":
        client.post(f"{path}/archive")
    if operation == "update":
        response = client.patch(path, json={"name": "Current"}, headers={"If-Match": '"1"'})
    else:
        response = client.post(f"{path}/{operation}", headers={"If-Match": '"1"'})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "version_conflict"

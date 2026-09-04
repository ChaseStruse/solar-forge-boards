"""Project API behavior."""

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

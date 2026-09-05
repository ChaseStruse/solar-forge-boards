"""OpenAPI publication and Solar Forge contract-flow tests."""

from flask.testing import FlaskClient


def test_openapi_document_is_generated_from_public_schemas(client: FlaskClient) -> None:
    """The published OpenAPI document names each public agent-facing operation."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    document: dict[str, object] = response.get_json()
    assert document["openapi"] == "3.1.0"
    paths: dict[str, object] = document["paths"]  # type: ignore[assignment]
    assert "/api/v1/projects" in paths
    assert "/api/v1/work-items/{work_item_id}/transitions" in paths
    assert "/api/v1/work-items/by-reference/{reference_number}" in paths
    work_item_collection: dict[str, object] = paths["/api/v1/projects/{project_id}/work-items"]  # type: ignore[assignment]
    parameters: list[dict[str, object]] = work_item_collection["parameters"]  # type: ignore[assignment]
    parameter_names: set[object] = {parameter["name"] for parameter in parameters}
    assert parameter_names >= {"cursor", "limit", "search", "tag_id"}
    components: dict[str, object] = document["components"]  # type: ignore[assignment]
    schemas: dict[str, object] = components["schemas"]  # type: ignore[assignment]
    assert "WorkItemCreate" in schemas
    assert "WorkItemRead" in schemas
    assert "WorkItemStatus" in schemas


def test_solar_forge_contract_flow(client: FlaskClient) -> None:
    """The documented agent flow creates, retrieves, and transitions a story."""
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Contract flow", "description": "Exercise published examples."},
    )
    assert project_response.status_code == 201
    project: dict[str, object] = project_response.get_json()["data"]
    project_id: str = str(project["id"])

    tags = client.get(f"/api/v1/projects/{project_id}/tags").get_json()["data"]
    coding_tag: dict[str, object] = next(tag for tag in tags if tag["name"] == "Coding")
    story_response = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={
            "title": "Publish the tool schema",
            "description": "Describe project and story operations.",
            "technical_description": "Use the generated OpenAPI document.",
            "tag_ids": [coding_tag["id"]],
        },
    )
    assert story_response.status_code == 201
    story: dict[str, object] = story_response.get_json()["data"]

    retrieved = client.get(f"/api/v1/work-items/by-reference/{story['reference_number']}")
    assert retrieved.status_code == 200
    assert retrieved.get_json()["data"]["id"] == story["id"]

    transitioned = client.post(
        f"/api/v1/work-items/{story['id']}/transitions", json={"status": "in_progress"}
    )
    assert transitioned.status_code == 200
    assert transitioned.get_json()["data"]["status"] == "in_progress"

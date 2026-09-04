"""Project tag vocabulary and story assignment behavior."""

from typing import cast

from flask.testing import FlaskClient


def test_projects_start_with_solar_forge_tag_vocabulary(
    client: FlaskClient, project_id: str
) -> None:
    """Every project begins with the four shared story categories."""
    response = client.get(f"/api/v1/projects/{project_id}/tags")
    assert response.status_code == 200
    tags: list[dict[str, str]] = response.get_json()["data"]
    assert {tag["name"]: tag["color"] for tag in tags} == {
        "Business": "#ff5fa2",
        "Coding": "#63f5c4",
        "Configuration": "#6aa9ff",
        "Spike": "#aa7cff",
    }


def test_custom_tag_creation_is_case_insensitively_unique(
    client: FlaskClient, project_id: str
) -> None:
    """People can extend a project's vocabulary without ambiguous duplicates."""
    created = client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"name": "Security", "color": "#F4A261"},
    )
    assert created.status_code == 201
    tag: dict[str, str] = created.get_json()["data"]
    assert tag["name"] == "Security"
    assert tag["color"] == "#f4a261"

    duplicate = client.post(
        f"/api/v1/projects/{project_id}/tags",
        json={"name": " security ", "color": "#000000"},
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "tag_name_conflict"

    events = client.get(f"/api/v1/projects/{project_id}/activity").get_json()["data"]
    assert any(
        event["event_type"] == "tag.created" and event["details"]["name"] == "Security"
        for event in events
    )


def test_story_tags_are_embedded_and_replaceable(client: FlaskClient, project_id: str) -> None:
    """Agent-facing story payloads include full tag objects on create and update."""
    tags = client.get(f"/api/v1/projects/{project_id}/tags").get_json()["data"]
    by_name: dict[str, dict[str, str]] = {tag["name"]: tag for tag in tags}
    created = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={
            "title": "Prototype agent memory",
            "tag_ids": [by_name["Coding"]["id"], by_name["Spike"]["id"]],
        },
    )
    assert created.status_code == 201
    story: dict[str, object] = created.get_json()["data"]
    story_tags = cast(list[dict[str, str]], story["tags"])
    assert [tag["name"] for tag in story_tags] == ["Coding", "Spike"]

    updated = client.patch(
        f"/api/v1/work-items/{story['id']}",
        json={"tag_ids": [by_name["Business"]["id"]]},
    )
    assert updated.status_code == 200
    assert [tag["name"] for tag in updated.get_json()["data"]["tags"]] == ["Business"]

    matching = client.get(
        f"/api/v1/projects/{project_id}/work-items",
        query_string={"tag_id": by_name["Business"]["id"]},
    )
    assert [item["id"] for item in matching.get_json()["data"]] == [story["id"]]

    not_matching = client.get(
        f"/api/v1/projects/{project_id}/work-items",
        query_string={"tag_id": by_name["Coding"]["id"]},
    )
    assert not_matching.get_json()["data"] == []


def test_story_rejects_tag_from_another_project(client: FlaskClient, project_id: str) -> None:
    """A story cannot reference a tag outside its project boundary."""
    other_project = client.post(
        "/api/v1/projects",
        json={"name": "Other Forge", "description": "Isolation test"},
    ).get_json()["data"]
    foreign_tag = client.get(f"/api/v1/projects/{other_project['id']}/tags").get_json()["data"][0]

    response = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={"title": "Cross-project story", "tag_ids": [foreign_tag["id"]]},
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_story_tags"

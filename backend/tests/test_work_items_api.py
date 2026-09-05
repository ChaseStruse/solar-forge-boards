"""Work-item API and activity behavior."""

from flask.testing import FlaskClient


def test_create_list_and_get_work_item(client: FlaskClient, project_id: str) -> None:
    """Work items can be created under and listed by project."""
    created = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={
            "title": "  Ship slice  ",
            "description": "End to end",
            "technical_description": "Expose a POST endpoint and persist the result.",
            "repository_url": "https://github.com/example/solar-forge",
        },
    )
    assert created.status_code == 201
    item: dict[str, object] = created.get_json()["data"]
    assert item["title"] == "Ship slice"
    assert isinstance(item["reference_number"], int)
    assert item["technical_description"] == "Expose a POST endpoint and persist the result."
    assert item["repository_url"] == "https://github.com/example/solar-forge"
    assert item["acceptance_criteria"] == []
    assert item["status"] == "todo"

    listed = client.get(f"/api/v1/projects/{project_id}/work-items")
    assert listed.get_json()["data"] == [item]

    fetched = client.get(f"/api/v1/work-items/{item['id']}")
    assert fetched.get_json()["data"] == item

    by_reference = client.get(f"/api/v1/work-items/by-reference/{item['reference_number']}")
    assert by_reference.status_code == 200
    assert by_reference.get_json()["data"] == item


def test_work_item_acceptance_criteria_search_and_sort(
    client: FlaskClient, project_id: str
) -> None:
    """The API provides validated criteria and server-side planning controls."""
    first = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={
            "title": "Document the API",
            "description": "Make the contract clear.",
            "acceptance_criteria": [
                "The reference covers every endpoint.",
                "Examples are valid JSON.",
            ],
        },
    )
    assert first.status_code == 201
    first_item = first.get_json()["data"]
    assert first_item["acceptance_criteria"] == [
        "The reference covers every endpoint.",
        "Examples are valid JSON.",
    ]
    client.post(f"/api/v1/projects/{project_id}/work-items", json={"title": "Build the board"})

    searched = client.get(
        f"/api/v1/projects/{project_id}/work-items?search=contract&sort=title&direction=desc"
    )
    assert searched.status_code == 200
    assert [item["id"] for item in searched.get_json()["data"]] == [first_item["id"]]

    updated = client.patch(
        f"/api/v1/work-items/{first_item['id']}", json={"acceptance_criteria": []}
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["acceptance_criteria"] == []

    invalid = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={"title": "Bad criteria", "acceptance_criteria": [" "]},
    )
    assert invalid.status_code == 422


def test_work_item_cursor_pagination_keeps_the_collection_query(
    client: FlaskClient, project_id: str
) -> None:
    """Cursor pages continue the same search and reject a mismatched query."""
    first = client.post(
        f"/api/v1/projects/{project_id}/work-items", json={"title": "Sync contracts"}
    ).get_json()["data"]
    second = client.post(
        f"/api/v1/projects/{project_id}/work-items", json={"title": "Sync plans"}
    ).get_json()["data"]
    client.post(f"/api/v1/projects/{project_id}/work-items", json={"title": "Unrelated"})

    first_page = client.get(
        f"/api/v1/projects/{project_id}/work-items",
        query_string={"search": "sync", "sort": "title", "limit": 1},
    )
    assert first_page.status_code == 200
    first_payload = first_page.get_json()
    assert [item["id"] for item in first_payload["data"]] == [first["id"]]
    cursor: str = first_payload["meta"]["next_cursor"]

    second_page = client.get(
        f"/api/v1/projects/{project_id}/work-items",
        query_string={
            "search": "sync",
            "sort": "title",
            "limit": 1,
            "cursor": cursor,
        },
    )
    assert second_page.status_code == 200
    second_payload = second_page.get_json()
    assert [item["id"] for item in second_payload["data"]] == [second["id"]]
    assert second_payload["meta"]["next_cursor"] is None

    mismatched = client.get(
        f"/api/v1/projects/{project_id}/work-items",
        query_string={"search": "different", "sort": "title", "limit": 1, "cursor": cursor},
    )
    assert mismatched.status_code == 422
    assert mismatched.get_json()["error"]["code"] == "invalid_cursor"


def test_work_item_cursor_requires_a_limit(client: FlaskClient, project_id: str) -> None:
    """A continuation token cannot accidentally change an unpaginated response."""
    response = client.get(
        f"/api/v1/projects/{project_id}/work-items", query_string={"cursor": "not-a-token"}
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"


def test_repository_link_must_be_http_or_https(client: FlaskClient, project_id: str) -> None:
    """Repository links are safe to render as clickable card links."""
    response = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        json={"title": "Unsafe link", "repository_url": "javascript:alert(1)"},
    )
    assert response.status_code == 422


def test_delete_work_item_preserves_activity_history(
    client: FlaskClient, project_id: str, work_item_id: str
) -> None:
    """Deleting a story removes it while retaining a useful audit trail."""
    deleted = client.delete(f"/api/v1/work-items/{work_item_id}")
    assert deleted.status_code == 204
    assert deleted.data == b""

    assert client.get(f"/api/v1/work-items/{work_item_id}").status_code == 404
    listed = client.get(f"/api/v1/projects/{project_id}/work-items")
    assert listed.get_json()["data"] == []

    events = client.get(f"/api/v1/projects/{project_id}/activity").get_json()["data"]
    created_event = next(event for event in events if event["event_type"] == "work_item.created")
    deleted_event = next(event for event in events if event["event_type"] == "work_item.deleted")
    assert created_event["work_item_id"] is None
    assert deleted_event["work_item_id"] is None
    assert deleted_event["details"] == {
        "status": "todo",
        "title": "Connect agent",
        "work_item_id": work_item_id,
    }

    assert client.delete(f"/api/v1/work-items/{work_item_id}").status_code == 404


def test_update_records_only_meaningful_changes(
    client: FlaskClient, project_id: str, work_item_id: str
) -> None:
    """Content edits are applied and represented in activity details."""
    updated = client.patch(
        f"/api/v1/work-items/{work_item_id}",
        json={
            "title": "Connect Solar Forge",
            "technical_description": "Use the stable agent contract.",
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["title"] == "Connect Solar Forge"

    activity = client.get(f"/api/v1/projects/{project_id}/activity")
    events: list[dict[str, object]] = activity.get_json()["data"]
    update_event: dict[str, object] = next(
        event for event in events if event["event_type"] == "work_item.updated"
    )
    details: dict[str, object] = update_event["details"]  # type: ignore[assignment]
    assert details["changes"] == {
        "technical_description": {"from": "", "to": "Use the stable agent contract."},
        "title": {"from": "Connect agent", "to": "Connect Solar Forge"},
    }


def test_valid_status_transition_creates_activity(
    client: FlaskClient, project_id: str, work_item_id: str
) -> None:
    """A valid transition changes status and emits an event."""
    response = client.post(
        f"/api/v1/work-items/{work_item_id}/transitions",
        json={"status": "in_progress"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "in_progress"

    events = client.get(f"/api/v1/projects/{project_id}/activity").get_json()["data"]
    assert any(
        event["event_type"] == "work_item.status_changed"
        and event["details"] == {"from": "todo", "to": "in_progress"}
        for event in events
    )


def test_todo_story_can_be_completed_directly(client: FlaskClient, work_item_id: str) -> None:
    """A story can move directly from Todo to Done when no intermediate work is needed."""
    response = client.post(
        f"/api/v1/work-items/{work_item_id}/transitions", json={"status": "done"}
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "done"


def test_priority_move_reorders_stories_within_their_lane(
    client: FlaskClient, project_id: str, work_item_id: str
) -> None:
    """Priority commands swap adjacent stories without changing their workflow status."""
    second = client.post(
        f"/api/v1/projects/{project_id}/work-items", json={"title": "Second priority"}
    ).get_json()["data"]
    third = client.post(
        f"/api/v1/projects/{project_id}/work-items", json={"title": "Third priority"}
    ).get_json()["data"]

    moved = client.post(f"/api/v1/work-items/{second['id']}/priority", json={"direction": "down"})
    assert moved.status_code == 200
    assert moved.get_json()["data"]["status"] == "todo"

    ordered = client.get(f"/api/v1/projects/{project_id}/work-items?sort=priority")
    assert [item["id"] for item in ordered.get_json()["data"]] == [
        work_item_id,
        third["id"],
        second["id"],
    ]
    event_types = {
        event["event_type"]
        for event in client.get(f"/api/v1/projects/{project_id}/activity").get_json()["data"]
    }
    assert "work_item.priority_changed" in event_types

    first_boundary = client.post(
        f"/api/v1/work-items/{work_item_id}/priority", json={"direction": "up"}
    )
    assert first_boundary.status_code == 200
    assert first_boundary.get_json()["data"]["priority"] == 1


def test_invalid_status_transition_is_rejected(client: FlaskClient, work_item_id: str) -> None:
    """Lifecycle rules keep cancelled stories from jumping directly to Done."""
    cancelled = client.post(
        f"/api/v1/work-items/{work_item_id}/transitions", json={"status": "cancelled"}
    )
    assert cancelled.status_code == 200
    response = client.post(
        f"/api/v1/work-items/{work_item_id}/transitions", json={"status": "done"}
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "invalid_status_transition"

    fetched = client.get(f"/api/v1/work-items/{work_item_id}")
    assert fetched.get_json()["data"]["status"] == "cancelled"


def test_generic_update_cannot_bypass_transition_rules(
    client: FlaskClient, work_item_id: str
) -> None:
    """Status is not accepted by the generic content-edit endpoint."""
    response = client.patch(
        f"/api/v1/work-items/{work_item_id}",
        json={"title": "Still governed", "status": "done"},
    )
    assert response.status_code == 422

    fetched = client.get(f"/api/v1/work-items/{work_item_id}")
    assert fetched.get_json()["data"]["status"] == "todo"


def test_create_work_item_requires_existing_project(client: FlaskClient) -> None:
    """The service protects the parent-child invariant."""
    response = client.post(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000/work-items",
        json={"title": "Orphan"},
    )
    assert response.status_code == 404


def test_activity_includes_project_and_work_item_creation(
    client: FlaskClient, project_id: str, work_item_id: str
) -> None:
    """Meaningful creations are recorded as immutable events."""
    del work_item_id
    events = client.get(f"/api/v1/projects/{project_id}/activity").get_json()["data"]
    event_types: set[str] = {event["event_type"] for event in events}
    assert event_types == {"project.created", "work_item.created"}

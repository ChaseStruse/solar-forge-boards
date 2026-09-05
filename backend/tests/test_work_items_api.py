"""Work-item API and activity behavior."""

from unittest.mock import Mock

import pytest
from flask.testing import FlaskClient

from backend.app.repositories import idempotency as idempotency_repository


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


def test_idempotency_key_replays_story_creation_without_a_duplicate(
    client: FlaskClient, project_id: str
) -> None:
    """A lost create response can be retried safely by an agent."""
    headers = {"Idempotency-Key": "story-create-retry"}
    payload = {"title": "Retry-safe story", "description": "Do not duplicate this work."}
    first = client.post(f"/api/v1/projects/{project_id}/work-items", headers=headers, json=payload)
    repeated = client.post(
        f"/api/v1/projects/{project_id}/work-items", headers=headers, json=payload
    )

    assert first.status_code == repeated.status_code == 201
    assert first.get_json() == repeated.get_json()
    listed = client.get(f"/api/v1/projects/{project_id}/work-items").get_json()["data"]
    assert [item["title"] for item in listed] == ["Retry-safe story"]

    reused = client.post(
        f"/api/v1/projects/{project_id}/work-items",
        headers=headers,
        json={"title": "Different request"},
    )
    assert reused.status_code == 409
    assert reused.get_json()["error"]["code"] == "idempotency_key_reused"


def test_story_conditional_write_rejects_a_stale_etag(
    client: FlaskClient, work_item_id: str
) -> None:
    """A stale agent cannot overwrite a newer story edit."""
    fetched = client.get(f"/api/v1/work-items/{work_item_id}")
    first = client.patch(
        f"/api/v1/work-items/{work_item_id}",
        headers={"If-Match": fetched.headers["ETag"]},
        json={"title": "Newer title"},
    )
    assert first.status_code == 200
    assert first.headers["ETag"] == '"2"'

    stale = client.patch(
        f"/api/v1/work-items/{work_item_id}",
        headers={"If-Match": fetched.headers["ETag"]},
        json={"title": "Stale overwrite"},
    )
    assert stale.status_code == 409
    assert stale.get_json()["error"]["code"] == "version_conflict"


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
        "correlation_id": deleted.headers["X-Correlation-ID"],
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
        and event["details"]
        == {
            "from": "todo",
            "to": "in_progress",
            "correlation_id": response.headers["X-Correlation-ID"],
        }
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


def test_reference_numbers_survive_deletion(client: FlaskClient, project_id: str) -> None:
    """A deleted story reference must never point to a later story."""
    collection = f"/api/v1/projects/{project_id}/work-items"
    first = client.post(collection, json={"title": "Original"}).get_json()["data"]
    client.delete(f"/api/v1/work-items/{first['id']}")
    second = client.post(collection, json={"title": "Replacement"}).get_json()["data"]
    assert second["reference_number"] > first["reference_number"]
    assert (
        client.get(f"/api/v1/work-items/by-reference/{first['reference_number']}").status_code
        == 404
    )


@pytest.mark.parametrize("operation", ["update", "transitions", "priority"])
def test_stale_noop_story_write_is_rejected(
    client: FlaskClient, work_item_id: str, operation: str
) -> None:
    """No-op commands still enforce an agent's supplied revision."""
    path = f"/api/v1/work-items/{work_item_id}"
    client.patch(path, json={"title": "Current"})
    headers = {"If-Match": '"1"'}
    if operation == "update":
        response = client.patch(path, json={"title": "Current"}, headers=headers)
    else:
        payload = {"status": "todo"} if operation == "transitions" else {"direction": "up"}
        response = client.post(f"{path}/{operation}", json=payload, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "version_conflict"


def test_idempotent_response_failure_rolls_back_everything(
    client: FlaskClient, project_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed response record cannot leave either a story or a stuck reservation."""
    collection = f"/api/v1/projects/{project_id}/work-items"
    headers = {"Idempotency-Key": "response-failure"}
    with monkeypatch.context() as scoped:
        scoped.setattr(idempotency_repository, "complete_request", Mock(side_effect=RuntimeError))
        with pytest.raises(RuntimeError):
            client.post(collection, json={"title": "Retry"}, headers=headers)
    assert client.get(collection).get_json()["data"] == []
    events = client.get(f"/api/v1/projects/{project_id}/activity").get_json()["data"]
    assert [event["event_type"] for event in events] == ["project.created"]
    first = client.post(collection, json={"title": "Retry"}, headers=headers)
    replay = client.post(collection, json={"title": "Retry"}, headers=headers)
    assert first.status_code == replay.status_code == 201
    assert first.get_json() == replay.get_json()
    assert len(client.get(collection).get_json()["data"]) == 1


@pytest.mark.parametrize("sort", ["priority", "created_at", "updated_at", "title", "status"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_paginated_tag_filter_matches_complete_collection(
    client: FlaskClient, project_id: str, sort: str, direction: str
) -> None:
    """SQL pagination preserves OR tags, ties, ordering, and complete embedded tags."""
    collection = f"/api/v1/projects/{project_id}/work-items"
    tags = client.get(f"/api/v1/projects/{project_id}/tags").get_json()["data"]
    selected = [tag["id"] for tag in tags[:2]]
    for index in range(6):
        client.post(
            collection,
            json={
                "title": f"Match {index // 2}",
                "tag_ids": selected if index < 4 else [selected[0]],
            },
        )
    client.post(collection, json={"title": "Match excluded"})
    query = [("tag_id", tag_id) for tag_id in selected]
    query += [
        ("tag_id", selected[0]),
        ("search", "Match"),
        ("sort", sort),
        ("direction", direction),
    ]
    expected = client.get(collection, query_string=query).get_json()["data"]
    collected = []
    cursor = None
    for _ in range(6):
        page_query = [*query, ("limit", "2")]
        if cursor is not None:
            page_query.append(("cursor", cursor))
        response = client.get(collection, query_string=page_query)
        assert response.status_code == 200
        page = response.get_json()
        collected.extend(page["data"])
        cursor = page["meta"]["next_cursor"]
        if cursor is None:
            break
    assert cursor is None
    assert len(expected) == 6
    assert collected == expected


def test_deleted_cursor_anchor_is_rejected(client: FlaskClient, project_id: str) -> None:
    """A cursor whose last story no longer exists retains the documented error."""
    collection = f"/api/v1/projects/{project_id}/work-items"
    for title in ["First", "Second"]:
        client.post(collection, json={"title": title})
    page = client.get(collection, query_string={"limit": 1}).get_json()
    client.delete(f"/api/v1/work-items/{page['data'][0]['id']}")
    response = client.get(
        collection, query_string={"limit": 1, "cursor": page["meta"]["next_cursor"]}
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "invalid_cursor"


def test_create_and_update_share_normalization(client: FlaskClient, project_id: str) -> None:
    """Creation and partial updates apply identical shared field rules."""
    collection = f"/api/v1/projects/{project_id}/work-items"
    tag = client.get(f"/api/v1/projects/{project_id}/tags").get_json()["data"][0]["id"]
    payload = {
        "title": "  Normalized  ",
        "repository_url": " https://example.com/repo ",
        "acceptance_criteria": ["  Criterion  "],
        "tag_ids": [tag, tag],
    }
    first = client.post(collection, json=payload).get_json()["data"]
    second = client.post(collection, json={"title": "Other"}).get_json()["data"]
    updated = client.patch(f"/api/v1/work-items/{second['id']}", json=payload).get_json()["data"]
    for field in ["title", "repository_url", "acceptance_criteria", "tags"]:
        assert first[field] == updated[field]
    assert first["title"] == "Normalized"
    assert first["acceptance_criteria"] == ["Criterion"]
    assert len(first["tags"]) == 1

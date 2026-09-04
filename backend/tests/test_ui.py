"""Server-rendered and HTMX presentation tests."""

from flask.testing import FlaskClient


def test_projects_page_and_board_render(client: FlaskClient, project_id: str) -> None:
    """The human-facing workspace renders projects and board columns."""
    projects = client.get("/ui/projects")
    assert projects.status_code == 200
    assert b"Solar Forge Boards" in projects.data

    board = client.get(f"/ui/projects/{project_id}")
    assert board.status_code == 200
    assert b"Project board" in board.data
    assert b"In Progress" in board.data
    assert b"Forge a story" in board.data
    assert b"Technical description" in board.data
    assert b"Acceptance criteria" in board.data
    assert b"Search stories" in board.data
    assert b">Activity<" in board.data
    assert b"Activity history" not in board.data
    assert b'class="tag-filter-menu"' in board.data
    assert b'aria-label="Filter stories by tag"' in board.data
    assert b"Tags" in board.data
    assert b"Coding" in board.data
    assert b"Spike" in board.data
    assert b"Customize" in board.data
    assert b"Create a project tag" in board.data
    assert b"Board view" in board.data
    assert b"All lanes" in board.data
    assert b"Work queue" in board.data
    assert b"Focus" in board.data
    assert b"Delivery" in board.data
    assert b"Visible lanes" in board.data
    assert f'data-project-id="{project_id}"'.encode() in board.data

    activity = client.get(f"/ui/projects/{project_id}?tab=activity")
    assert activity.status_code == 200
    assert b"Activity history" in activity.data
    assert b'id="board"' not in activity.data


def test_htmx_create_edit_and_transition_refresh_board(
    client: FlaskClient, project_id: str
) -> None:
    """HTMX story writes return refreshed board fragments."""
    tags = client.get(f"/api/v1/projects/{project_id}/tags").get_json()["data"]
    coding_tag = next(tag for tag in tags if tag["name"] == "Coding")
    created = client.post(
        f"/ui/projects/{project_id}/work-items",
        data={
            "title": "HTMX card",
            "description": "A human-friendly explanation.",
            "technical_description": "A typed service boundary.",
            "acceptance_criteria": "The card is visible.\nThe workflow is available.",
            "repository_url": "https://github.com/example/solar-forge",
            "tag_ids": coding_tag["id"],
        },
        headers={"HX-Request": "true"},
    )
    assert created.status_code == 201
    assert b'id="board"' in created.data
    assert b"HTMX card" in created.data
    assert b"A human-friendly explanation." in created.data
    assert b"A typed service boundary." in created.data
    assert b"Open repository" in created.data
    assert b"Edit story" in created.data
    assert b"Save changes" in created.data
    assert b'draggable="true"' in created.data
    assert b'data-allowed-statuses="' in created.data
    assert b'class="drag-transition-form"' in created.data
    assert b"Drag the card to another lane" in created.data
    assert b'<select name="status"' not in created.data
    assert b"Delete story" in created.data
    assert b"This cannot be undone" in created.data
    assert b'class="tag-pill"' in created.data
    assert b"Coding" in created.data

    item_id: str = client.get(f"/api/v1/projects/{project_id}/work-items").get_json()["data"][0][
        "id"
    ]
    edited = client.post(
        f"/ui/work-items/{item_id}",
        data={
            "title": "Edited HTMX card",
            "description": "A clearer human-friendly explanation.",
            "technical_description": "An updated typed service boundary.",
            "repository_url": "https://github.com/example/solar-forge-boards",
            "tag_ids": coding_tag["id"],
        },
        headers={"HX-Request": "true"},
    )
    assert edited.status_code == 200
    assert b'id="board"' in edited.data
    assert b"Edited HTMX card" in edited.data
    assert b"An updated typed service boundary." in edited.data

    fetched = client.get(f"/api/v1/work-items/{item_id}").get_json()["data"]
    assert fetched["title"] == "Edited HTMX card"
    assert fetched["repository_url"] == "https://github.com/example/solar-forge-boards"

    moved = client.post(
        f"/ui/work-items/{item_id}/transitions",
        data={"status": "in_progress"},
        headers={"HX-Request": "true"},
    )
    assert moved.status_code == 200
    assert b"Edited HTMX card" in moved.data


def test_htmx_edit_error_stays_inside_open_editor(client: FlaskClient, work_item_id: str) -> None:
    """Invalid edits preserve the open form instead of replacing the board."""
    response = client.post(
        f"/ui/work-items/{work_item_id}",
        data={
            "title": "Still editable",
            "description": "",
            "technical_description": "",
            "repository_url": "javascript:alert(1)",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 422
    assert response.headers["HX-Retarget"] == f"#edit-error-{work_item_id}"
    assert response.headers["HX-Reswap"] == "innerHTML"
    assert b"Repository link must be a complete" in response.data


def test_htmx_delete_story_refreshes_board(client: FlaskClient, work_item_id: str) -> None:
    """Confirmed story deletion removes its card from the refreshed board."""
    response = client.post(
        f"/ui/work-items/{work_item_id}/delete",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert b'id="board"' in response.data
    assert b"Connect agent" not in response.data
    assert client.get(f"/api/v1/work-items/{work_item_id}").status_code == 404


def test_custom_tag_can_be_created_from_board(client: FlaskClient, project_id: str) -> None:
    """The board lets people extend their project's story vocabulary."""
    created = client.post(
        f"/ui/projects/{project_id}/tags",
        data={"name": "Security", "color": "#f4a261"},
    )
    assert created.status_code == 302
    board = client.get(created.headers["Location"])
    assert b"Security" in board.data

    duplicate = client.post(
        f"/ui/projects/{project_id}/tags",
        data={"name": "security", "color": "#000000"},
    )
    assert duplicate.status_code == 422
    assert b"already exists" in duplicate.data


def test_archived_project_board_is_read_only(client: FlaskClient, project_id: str) -> None:
    """An archived board visibly preserves history without inviting writes."""
    assert client.post(f"/ui/projects/{project_id}/archive").status_code == 302
    board = client.get(f"/ui/projects/{project_id}")
    assert b"This project is read-only." in board.data
    assert b"Restore project" in board.data
    assert b"Forge a story" not in board.data

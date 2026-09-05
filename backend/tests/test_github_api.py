"""Repository configuration, GitHub snapshots, and safe story defaults."""

from email.message import Message
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest
from flask.testing import FlaskClient

from backend.app.integrations.github import GitHubClient, GitHubFailure


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def request(self: GitHubClient, path: str) -> dict[str, Any]:
        calls.append(path)
        if path.startswith("missing/"):
            raise GitHubFailure("Not found or unavailable to the configured token.", status=404)
        if path.endswith("/releases/latest"):
            if path.startswith("empty/"):
                raise GitHubFailure("Not found or unavailable to the configured token.", status=404)
            return {
                "tag_name": "v1.0",
                "name": "First release",
                "body": "<script>alert(1)</script>",
                "published_at": "2026-09-05T12:00:00Z",
            }
        return {
            "description": "Repository context",
            "stargazers_count": 12,
            "forks_count": 3,
            "open_issues_count": 4,
            "default_branch": "main",
        }

    monkeypatch.setattr(GitHubClient, "request", request)
    return calls


def test_repository_update_defaults_and_preservation(client: FlaskClient, project_id: str) -> None:
    path = f"/api/v1/projects/{project_id}"
    result = client.patch(
        path,
        json={
            "repository_urls": [
                "https://github.com/Owner/Repo.git/",
                "https://github.com/owner/repo",
                "https://github.com/owner/second",
            ]
        },
    )
    assert result.status_code == 200
    assert result.json is not None
    assert result.get_json()["data"]["repository_urls"] == [
        "https://github.com/owner/repo",
        "https://github.com/owner/second",
    ]
    assert (
        client.patch(path, json={"description": "New"}).get_json()["data"]["repository_urls"]
        == result.get_json()["data"]["repository_urls"]
    )
    stale = client.patch(path, json={"repository_urls": []}, headers={"If-Match": '"1"'})
    assert stale.status_code == 409
    story = client.post(path + "/work-items", json={"title": "Default"}).get_json()["data"]
    assert story["repository_url"] == "https://github.com/owner/repo"
    empty = client.post(path + "/work-items", json={"title": "No link", "repository_url": ""})
    assert empty.get_json()["data"]["repository_url"] == ""
    custom = client.post(
        path + "/work-items", json={"title": "Other", "repository_url": "https://example.com/repo"}
    )
    assert custom.get_json()["data"]["repository_url"] == "https://example.com/repo"
    client.patch(path, json={"repository_urls": []})
    assert (
        client.get(f"/api/v1/work-items/{story['id']}").get_json()["data"]["repository_url"]
        == "https://github.com/owner/repo"
    )
    client.post(path + "/archive")
    assert (
        client.patch(path, json={"repository_urls": ["https://github.com/a/b"]}).status_code == 409
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://github.com.evil.com/a/b",
        "https://user@github.com/a/b",
        "https://github.com/a/b/issues",
        "https://github.com/a/b?token=x",
        "https://github.com/a/..",
        "https://localhost/a/b",
        "https://github.com/a/%2e%2e",
        "https://github.com/a/b#fragment",
    ],
)
def test_repository_urls_reject_unsafe_paths(
    client: FlaskClient, project_id: str, url: str
) -> None:
    assert (
        client.patch(f"/api/v1/projects/{project_id}", json={"repository_urls": [url]}).status_code
        == 422
    )


def test_github_snapshots_partial_failures_and_cache(
    client: FlaskClient,
    project_id: str,
    github: list[str],
) -> None:
    path = f"/api/v1/projects/{project_id}"
    client.patch(
        path,
        json={
            "repository_urls": [
                "https://github.com/owner/repo",
                "https://github.com/missing/repo",
                "https://github.com/empty/repo",
            ]
        },
    )
    response = client.get(path + "/repositories")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data[0]["stars"] == 12
    assert data[0]["release"]["tag"] == "v1.0"
    assert data[1]["error"] is not None
    assert data[2]["release"] is None and data[2]["release_error"] is None
    assert len(github) == 5
    assert client.get(path + "/repositories").get_json()["data"] == data
    assert len(github) == 5


def test_repository_create_and_bounds(client: FlaskClient) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"name": "Repositories", "repository_urls": ["https://github.com/a/b"]},
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["repository_urls"] == ["https://github.com/a/b"]
    assert (
        client.post(
            "/api/v1/projects",
            json={
                "name": "Too many",
                "repository_urls": [f"https://github.com/a/b{i}" for i in range(11)],
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("failure", [401, 403, 404, 429, 500, "network", "json", "oversize"])
def test_github_transport_sanitizes_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: int | str,
) -> None:
    """Do not expose upstream bodies or credentials when GitHub cannot be read."""

    class Opener:
        def open(self, request: Request, timeout: int) -> BytesIO:
            assert request.full_url == "https://api.github.com/repos/owner/repo"
            assert request.get_header("Authorization") == "Bearer secret-token"
            assert timeout == 5
            if isinstance(failure, int):
                raise HTTPError(request.full_url, failure, "secret upstream body", Message(), None)
            if failure == "network":
                raise URLError("secret network details")
            return BytesIO(b"x" * 2_000_001 if failure == "oversize" else b"not json")

    monkeypatch.setattr("backend.app.integrations.github.build_opener", lambda *args: Opener())
    with pytest.raises(GitHubFailure) as raised:
        GitHubClient("secret-token").request("owner/repo")
    assert "secret" not in str(raised.value)


def test_github_cache_isolated_per_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A different credential context must never receive another client's private snapshot."""
    calls: list[str] = []

    def request(self: GitHubClient, path: str) -> dict[str, Any]:
        calls.append(path)
        raise GitHubFailure("Denied")

    monkeypatch.setattr(GitHubClient, "request", request)
    first = GitHubClient("first")
    second = GitHubClient("second")
    first.repository("https://github.com/a/b")
    first.repository("https://github.com/a/b")
    second.repository("https://github.com/a/b")
    assert len(calls) == 2

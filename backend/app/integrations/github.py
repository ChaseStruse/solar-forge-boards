"""Read-only GitHub client with bounded requests and a short, process-local cache."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener

from backend.app.integrations.http import NoRedirects
from backend.app.schemas.github import GitHubRelease, GitHubRepository


class GitHubFailure(Exception):
    """Sanitized external failure suitable for display without credentials."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubClient:
    """Fetch only fixed endpoints derived from validated project repository URLs."""

    def __init__(self, token: str = "") -> None:
        self._token = token
        self._cache: dict[str, tuple[float, GitHubRepository]] = {}
        self._lock = Lock()

    def request(self, path: str) -> dict[str, Any]:
        """Fetch an object; redact upstream bodies and credentials from all failures."""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Solar-Forge-Boards",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        req = Request("https://api.github.com/repos/" + path, headers=headers)
        try:
            with build_opener(NoRedirects()).open(req, timeout=5) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise GitHubFailure("GitHub returned an oversized response.")
                value: Any = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("Expected an object")
                return value
        except HTTPError as error:
            error.close()
            if error.code == 404:
                raise GitHubFailure(
                    "Not found or unavailable to the configured token.", status=404
                ) from None
            if error.code in {401, 403, 429}:
                raise GitHubFailure(
                    "GitHub access denied or rate limited. Check token permissions or try later."
                ) from None
            raise GitHubFailure(
                "GitHub is temporarily unavailable or the repository has moved."
            ) from None
        except URLError, OSError, ValueError:
            raise GitHubFailure("Could not read GitHub. Try again later.") from None

    def repository(self, url: str) -> GitHubRepository:
        """Return metadata and release status without failing other repositories."""
        with self._lock:
            cached = self._cache.get(url)
            if cached and monotonic() - cached[0] < 60:
                return cached[1].model_copy(deep=True)
        name = url.removeprefix("https://github.com/")
        snapshot = GitHubRepository(url=url, name=name)
        try:
            data = self.request(name)
            snapshot.description = str(data.get("description") or "")
            snapshot.stars = int(data["stargazers_count"])
            snapshot.forks = int(data["forks_count"])
            snapshot.open_issues = int(data["open_issues_count"])
            snapshot.default_branch = str(data["default_branch"])
        except (GitHubFailure, KeyError, TypeError, ValueError) as error:
            snapshot.error = (
                str(error)
                if isinstance(error, GitHubFailure)
                else "Invalid GitHub repository data."
            )
        if snapshot.error is None:
            try:
                release = self.request(name + "/releases/latest")
                tag = str(release["tag_name"])
                snapshot.release = GitHubRelease(
                    name=str(release.get("name") or tag),
                    tag=tag,
                    url=url + "/releases/tag/" + quote(tag, safe=""),
                    notes=str(release.get("body") or ""),
                    published_at=release.get("published_at"),
                )
            except GitHubFailure as error:
                # A release 404 is expected for repositories without a published stable release.
                if error.status != 404:
                    snapshot.release_error = str(error)
            except KeyError, TypeError, ValueError:
                snapshot.release_error = "Invalid GitHub release data."
        with self._lock:
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[url] = (monotonic(), snapshot)
        return snapshot.model_copy(deep=True)

    def repositories(self, urls: list[str]) -> list[GitHubRepository]:
        """Bound concurrency while keeping the configured repository order."""
        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(self.repository, urls))

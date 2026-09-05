"""Presentation-ready GitHub repository snapshots."""

from backend.app.schemas.common import ApiModel


class GitHubRelease(ApiModel):
    """Latest published stable release."""

    name: str
    tag: str
    url: str
    notes: str
    published_at: str | None = None


class GitHubRepository(ApiModel):
    """One repository's independent success or failure state."""

    url: str
    name: str
    description: str = ""
    stars: int | None = None
    forks: int | None = None
    open_issues: int | None = None
    default_branch: str | None = None
    release: GitHubRelease | None = None
    error: str | None = None
    release_error: str | None = None

"""Project request and response schemas."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.common import ApiModel


def normalize_repositories(values: list[str]) -> list[str]:
    """Restrict GitHub API lookups to canonical repository paths on github.com."""
    result: list[str] = []
    for value in values:
        match = re.fullmatch(
            r"https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})/?",
            value.strip(),
            re.IGNORECASE,
        )
        if match is None or match[2] in {".", ".."}:
            raise ValueError("Use complete https://github.com/owner/repository URLs.")
        repo = match[2].removesuffix(".git")
        if not repo or repo in {".", ".."}:
            raise ValueError("A repository name is required.")
        url = f"https://github.com/{match[1]}/{repo}".lower()
        if url not in result:
            result.append(url)
    return result


class ProjectCreate(ApiModel):
    """Input for creating a project."""

    repository_urls: list[str] = Field(default_factory=list, max_length=10)

    _repositories = field_validator("repository_urls")(normalize_repositories)

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        """Reject whitespace-only names and normalize outer whitespace."""
        stripped: str = value.strip()
        if not stripped:
            raise ValueError("Project name cannot be blank.")
        return stripped


class ProjectRead(ApiModel):
    """Public project representation."""

    id: UUID
    repository_urls: list[str] = Field(default_factory=list)
    name: str
    description: str
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(ApiModel):
    """Partial input for editing project details."""

    repository_urls: list[str] | None = Field(default=None, max_length=10)

    @field_validator("repository_urls")
    @classmethod
    def validate_repositories(cls, value: list[str] | None) -> list[str] | None:
        """Normalize a supplied replacement collection."""
        return None if value is None else normalize_repositories(value)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        """Reject blank names and normalize outer whitespace."""
        if value is None:
            return None
        stripped: str = value.strip()
        if not stripped:
            raise ValueError("Project name cannot be blank.")
        return stripped

    @model_validator(mode="after")
    def ensure_update_present(self) -> ProjectUpdate:
        """Require at least one editable field."""
        if self.name is None and self.description is None and self.repository_urls is None:
            raise ValueError("At least one field must be provided.")
        return self

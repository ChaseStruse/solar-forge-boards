"""Work-item request and response schemas."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.domain import WorkItemStatus
from backend.app.schemas.common import ApiModel
from backend.app.schemas.tags import TagRead


def strip_title(value: str) -> str:
    """Reject blank titles and normalize outer whitespace."""
    stripped: str = value.strip()
    if not stripped:
        raise ValueError("Work-item title cannot be blank.")
    return stripped


def validate_repository_url(value: str) -> str:
    """Allow an empty value or a complete HTTP(S) repository URL."""
    stripped: str = value.strip()
    if not stripped:
        return ""
    parsed = urlsplit(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Repository link must be a complete http:// or https:// URL.")
    return stripped


def unique_tag_ids(value: list[UUID]) -> list[UUID]:
    """Deduplicate tag assignments while preserving request order."""
    return list(dict.fromkeys(value))


def normalize_acceptance_criteria(value: list[str]) -> list[str]:
    """Normalize checklist items and reject blank or oversized entries."""
    normalized: list[str] = [criterion.strip() for criterion in value]
    if any(not criterion for criterion in normalized):
        raise ValueError("Acceptance criteria cannot contain blank items.")
    if any(len(criterion) > 500 for criterion in normalized):
        raise ValueError("Each acceptance criterion must be at most 500 characters.")
    return normalized


class WorkItemCreate(ApiModel):
    """Input for creating a work item."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    technical_description: str = Field(default="", max_length=20000)
    repository_url: str = Field(default="", max_length=2048)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=100)
    tag_ids: list[UUID] = Field(default_factory=list, max_length=20)

    _strip_title = field_validator("title")(strip_title)

    _validate_repository_url = field_validator("repository_url")(validate_repository_url)

    _unique_tag_ids = field_validator("tag_ids")(unique_tag_ids)

    _normalize_acceptance_criteria = field_validator("acceptance_criteria")(
        normalize_acceptance_criteria
    )


class WorkItemUpdate(ApiModel):
    """Partial input for editing work-item content."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    technical_description: str | None = Field(default=None, max_length=20000)
    repository_url: str | None = Field(default=None, max_length=2048)
    acceptance_criteria: list[str] | None = Field(default=None, max_length=100)
    tag_ids: list[UUID] | None = Field(default=None, max_length=20)

    @field_validator("title")
    @classmethod
    def strip_optional_title(cls, value: str | None) -> str | None:
        """Normalize an optional title."""
        if value is None:
            return None
        return strip_title(value)

    @field_validator("repository_url")
    @classmethod
    def validate_optional_repository_url(cls, value: str | None) -> str | None:
        """Normalize an optional repository URL while allowing it to be cleared."""
        if value is None:
            return None
        return validate_repository_url(value)

    @field_validator("tag_ids")
    @classmethod
    def unique_optional_tag_ids(cls, value: list[UUID] | None) -> list[UUID] | None:
        """Deduplicate optional tag assignments."""
        return None if value is None else unique_tag_ids(value)

    @field_validator("acceptance_criteria")
    @classmethod
    def normalize_optional_acceptance_criteria(cls, value: list[str] | None) -> list[str] | None:
        """Apply the creation checklist rules to an optional replacement list."""
        return None if value is None else normalize_acceptance_criteria(value)

    @model_validator(mode="after")
    def ensure_update_present(self) -> WorkItemUpdate:
        """Require at least one editable field."""
        if all(
            value is None
            for value in (
                self.title,
                self.description,
                self.technical_description,
                self.repository_url,
                self.acceptance_criteria,
                self.tag_ids,
            )
        ):
            raise ValueError("At least one field must be provided.")
        return self


class StatusTransition(ApiModel):
    """Input for a work-item status transition."""

    status: WorkItemStatus


class PriorityMove(ApiModel):
    """Input for moving a story within its current workflow lane."""

    direction: Literal["up", "down"]


class WorkItemListFilter(ApiModel):
    """Optional collection search and ordering controls."""

    search: str | None = Field(default=None, max_length=200)
    sort: Literal["priority", "created_at", "updated_at", "title", "status"] = "priority"
    direction: Literal["asc", "desc"] = "asc"
    tag_ids: list[UUID] = Field(default_factory=list, max_length=20)
    limit: int | None = Field(default=None, ge=1, le=100)
    cursor: str | None = Field(default=None, max_length=2048)

    @field_validator("search")
    @classmethod
    def strip_optional_search(cls, value: str | None) -> str | None:
        """Normalize a blank search to no filter."""
        if value is None:
            return None
        stripped: str = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def require_limit_for_cursor(self) -> WorkItemListFilter:
        """Keep cursor traversal explicit and bounded."""
        if self.cursor is not None and self.limit is None:
            raise ValueError("A cursor requires a limit.")
        return self


class WorkItemRead(ApiModel):
    """Public work-item representation."""

    id: UUID
    reference_number: int
    project_id: UUID
    title: str
    description: str
    technical_description: str
    repository_url: str
    acceptance_criteria: list[str]
    tags: list[TagRead]
    status: WorkItemStatus
    priority: int
    version: int
    created_at: datetime
    updated_at: datetime

"""Work-item request and response schemas."""

from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.domain import WorkItemStatus
from backend.app.schemas.common import ApiModel
from backend.app.schemas.tags import TagRead


class WorkItemCreate(ApiModel):
    """Input for creating a work item."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    technical_description: str = Field(default="", max_length=20000)
    repository_url: str = Field(default="", max_length=2048)
    tag_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        """Reject blank titles and normalize outer whitespace."""
        stripped: str = value.strip()
        if not stripped:
            raise ValueError("Work-item title cannot be blank.")
        return stripped

    @field_validator("repository_url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        """Allow an empty value or a complete HTTP(S) repository URL."""
        stripped: str = value.strip()
        if not stripped:
            return ""
        parsed = urlsplit(stripped)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Repository link must be a complete http:// or https:// URL.")
        return stripped

    @field_validator("tag_ids")
    @classmethod
    def unique_tag_ids(cls, value: list[UUID]) -> list[UUID]:
        """Deduplicate tag assignments while preserving request order."""
        return list(dict.fromkeys(value))


class WorkItemUpdate(ApiModel):
    """Partial input for editing work-item content."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    technical_description: str | None = Field(default=None, max_length=20000)
    repository_url: str | None = Field(default=None, max_length=2048)
    tag_ids: list[UUID] | None = Field(default=None, max_length=20)

    @field_validator("title")
    @classmethod
    def strip_optional_title(cls, value: str | None) -> str | None:
        """Normalize an optional title."""
        if value is None:
            return None
        stripped: str = value.strip()
        if not stripped:
            raise ValueError("Work-item title cannot be blank.")
        return stripped

    @field_validator("repository_url")
    @classmethod
    def validate_optional_repository_url(cls, value: str | None) -> str | None:
        """Normalize an optional repository URL while allowing it to be cleared."""
        if value is None:
            return None
        return WorkItemCreate.validate_repository_url(value)

    @field_validator("tag_ids")
    @classmethod
    def unique_optional_tag_ids(cls, value: list[UUID] | None) -> list[UUID] | None:
        """Deduplicate optional tag assignments."""
        return None if value is None else list(dict.fromkeys(value))

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
                self.tag_ids,
            )
        ):
            raise ValueError("At least one field must be provided.")
        return self


class StatusTransition(ApiModel):
    """Input for a work-item status transition."""

    status: WorkItemStatus


class WorkItemRead(ApiModel):
    """Public work-item representation."""

    id: UUID
    project_id: UUID
    title: str
    description: str
    technical_description: str
    repository_url: str
    tags: list[TagRead]
    status: WorkItemStatus
    created_at: datetime
    updated_at: datetime

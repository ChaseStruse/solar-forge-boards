"""Project-tag request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from backend.app.schemas.common import ApiModel


class TagCreate(ApiModel):
    """Input for creating a project-scoped tag."""

    name: str = Field(min_length=1, max_length=60)
    color: str = Field(default="#63f5c4", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        """Reject whitespace-only tag names and normalize outer whitespace."""
        stripped: str = value.strip()
        if not stripped:
            raise ValueError("Tag name cannot be blank.")
        return stripped

    @field_validator("color")
    @classmethod
    def normalize_color(cls, value: str) -> str:
        """Store hexadecimal colors consistently."""
        return value.lower()


class TagRead(ApiModel):
    """Public tag representation used by people and agents."""

    id: UUID
    project_id: UUID
    name: str
    color: str
    created_at: datetime


class TagFilter(ApiModel):
    """Validated tag filters for story-list queries."""

    tag_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("tag_ids")
    @classmethod
    def unique_tag_ids(cls, value: list[UUID]) -> list[UUID]:
        """Deduplicate repeated query parameters."""
        return list(dict.fromkeys(value))

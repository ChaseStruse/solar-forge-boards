"""Project request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.common import ApiModel


class ProjectCreate(ApiModel):
    """Input for creating a project."""

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
    name: str
    description: str
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(ApiModel):
    """Partial input for editing project details."""

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
        if self.name is None and self.description is None:
            raise ValueError("At least one field must be provided.")
        return self

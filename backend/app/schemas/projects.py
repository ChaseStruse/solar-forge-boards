"""Project request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

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
    created_at: datetime
    updated_at: datetime

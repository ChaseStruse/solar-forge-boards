"""Shared schema helpers."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base schema with API-friendly serialization defaults."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ActivityEventRead(ApiModel):
    """Public activity-event representation."""

    id: UUID
    project_id: UUID
    work_item_id: UUID | None
    event_type: str
    details: dict[str, Any]
    created_at: datetime

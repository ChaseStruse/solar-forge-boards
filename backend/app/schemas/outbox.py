"""Public delivery diagnostics without internal worker lease tokens."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from backend.app.schemas.common import ApiModel

DeliveryStatus = Literal["pending", "processing", "delivered", "failed"]


class OutboxFilter(ApiModel):
    status: DeliveryStatus | None = None
    limit: int = Field(default=50, ge=1, le=100)


class OutboxRead(ApiModel):
    id: UUID
    project_id: UUID
    event_type: str
    payload: dict[str, Any]
    status: DeliveryStatus
    attempts: int
    attempt_limit: int
    next_attempt_at: datetime
    lease_until: datetime | None
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime

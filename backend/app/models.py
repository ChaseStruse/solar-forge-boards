"""SQLAlchemy Core table definitions."""

from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.schema import Column

metadata: MetaData = MetaData()

story_reference_counter: Table = Table(
    "story_reference_counter",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("value", Integer, nullable=False),
    CheckConstraint("id = 1", name="ck_story_reference_counter_singleton"),
)

projects: Table = Table(
    "projects",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("name", String(120), nullable=False, unique=True),
    Column("repository_urls", JSON, nullable=False, server_default="[]"),
    Column("description", Text, nullable=False, server_default=""),
    Column("archived_at", DateTime(timezone=True), nullable=True),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

work_items: Table = Table(
    "work_items",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("reference_number", Integer, nullable=False, unique=True),
    Column(
        "project_id",
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=False, server_default=""),
    Column("technical_description", Text, nullable=False, server_default=""),
    Column("repository_url", String(2048), nullable=False, server_default=""),
    Column("acceptance_criteria", JSON, nullable=False, server_default="[]"),
    Column("status", String(32), nullable=False, server_default="todo"),
    Column("priority", Integer, nullable=False, server_default="1"),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint(
        "status IN ('todo', 'in_progress', 'blocked', 'done', 'cancelled')",
        name="ck_work_items_status",
    ),
)
Index("ix_work_items_project_status", work_items.c.project_id, work_items.c.status)

tags: Table = Table(
    "tags",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "project_id",
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(60), nullable=False),
    Column("color", String(7), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("project_id", "name", name="uq_tags_project_name"),
)
Index("ix_tags_project", tags.c.project_id)

work_item_tags: Table = Table(
    "work_item_tags",
    metadata,
    Column(
        "work_item_id",
        Uuid(as_uuid=True),
        ForeignKey("work_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Uuid(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
Index("ix_work_item_tags_tag", work_item_tags.c.tag_id)

activity_events: Table = Table(
    "activity_events",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "project_id",
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "work_item_id",
        Uuid(as_uuid=True),
        ForeignKey("work_items.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("event_type", String(64), nullable=False),
    Column("details", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index(
    "ix_activity_events_project_created", activity_events.c.project_id, activity_events.c.created_at
)

idempotency_requests: Table = Table(
    "idempotency_requests",
    metadata,
    Column("key", String(255), primary_key=True),
    Column("request_scope", String(255), nullable=False),
    Column("request_fingerprint", String(64), nullable=False),
    Column("response_status", Integer, nullable=True),
    Column("response_data", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class ProjectRow(TypedDict):
    """Typed project record returned by the repository."""

    id: UUID
    name: str
    repository_urls: list[str]
    description: str
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class WorkItemRow(TypedDict):
    """Typed work-item record returned by the repository."""

    id: UUID
    reference_number: int
    project_id: UUID
    title: str
    description: str
    technical_description: str
    repository_url: str
    acceptance_criteria: list[str]
    status: str
    priority: int
    version: int
    created_at: datetime
    updated_at: datetime


class TagRow(TypedDict):
    """Typed project tag returned by the repository."""

    id: UUID
    project_id: UUID
    name: str
    color: str
    created_at: datetime


class WorkItemWithTagsRow(WorkItemRow):
    """Work item enriched with its ordered tag collection."""

    tags: list[TagRow]


class ActivityRow(TypedDict):
    """Typed activity-event record returned by the repository."""

    id: UUID
    project_id: UUID
    work_item_id: UUID | None
    event_type: str
    details: dict[str, Any]
    created_at: datetime


class IdempotencyRequestRow(TypedDict):
    """Persisted result of one replay-safe JSON write request."""

    key: str
    request_scope: str
    request_fingerprint: str
    response_status: int | None
    response_data: dict[str, Any] | None
    created_at: datetime

"""add transactional event outbox

Revision ID: 4e8837ce388a
Revises: 923c2fb8b1fc
Create Date: 2026-09-05 14:47:47.683974
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e8837ce388a"
down_revision: str | Sequence[str] | None = "923c2fb8b1fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempt_limit", sa.Integer(), server_default="8", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'failed')", name="ck_outbox_status"
        ),
        sa.CheckConstraint("attempts >= 0 AND attempt_limit > 0", name="ck_outbox_attempts"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_due", "outbox_events", ["status", "next_attempt_at"], unique=False)
    op.create_index(
        "ix_outbox_project_created", "outbox_events", ["project_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_project_created", table_name="outbox_events")
    op.drop_index("ix_outbox_due", table_name="outbox_events")
    op.drop_table("outbox_events")

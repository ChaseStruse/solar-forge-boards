"""Add resource revisions and API idempotency request storage.

Revision ID: 20260905_0008
Revises: 20260904_0007
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0008"
down_revision: str | Sequence[str] | None = "20260904_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill revision counters without changing existing resource content."""
    op.add_column(
        "projects", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "work_items", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )
    op.create_table(
        "idempotency_requests",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_scope", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Remove write-safety persistence."""
    op.drop_table("idempotency_requests")
    op.drop_column("work_items", "version")
    op.drop_column("projects", "version")

"""Add persisted priority ordering within project workflow lanes.

Revision ID: 20260904_0006
Revises: 20260904_0005
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0006"
down_revision: str | Sequence[str] | None = "20260904_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Give existing stories a stable priority in each project's workflow lane."""
    op.add_column("work_items", sa.Column("priority", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY project_id, status ORDER BY created_at, id
            ) AS position
            FROM work_items
        )
        UPDATE work_items
        SET priority = ranked.position
        FROM ranked
        WHERE work_items.id = ranked.id
        """
    )
    op.alter_column("work_items", "priority", nullable=False, server_default="1")
    op.create_index(
        "ix_work_items_project_status_priority", "work_items", ["project_id", "status", "priority"]
    )


def downgrade() -> None:
    """Remove persisted story priority ordering."""
    op.drop_index("ix_work_items_project_status_priority", table_name="work_items")
    op.drop_column("work_items", "priority")

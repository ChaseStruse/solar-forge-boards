"""Preserve story reference allocation across deletion.

Revision ID: 20260905_0009
Revises: 20260905_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0009"
down_revision: str | Sequence[str] | None = "20260905_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Seed a durable counter without renumbering existing stories."""
    op.create_table(
        "story_reference_counter",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_story_reference_counter_singleton"),
    )
    op.execute(
        "INSERT INTO story_reference_counter (id, value) "
        "SELECT 1, COALESCE(MAX(reference_number), 0) FROM work_items"
    )


def downgrade() -> None:
    """Remove allocation state while retaining all projects and stories."""
    op.drop_table("story_reference_counter")

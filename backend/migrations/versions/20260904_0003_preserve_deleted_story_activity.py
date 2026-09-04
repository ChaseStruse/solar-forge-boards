"""Preserve activity events after their story is deleted.

Revision ID: 20260904_0003
Revises: 20260904_0002
Create Date: 2026-09-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260904_0003"
down_revision: str | Sequence[str] | None = "20260904_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Keep activity rows and clear their story reference on deletion."""
    op.drop_constraint(
        "activity_events_work_item_id_fkey",
        "activity_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "activity_events_work_item_id_fkey",
        "activity_events",
        "work_items",
        ["work_item_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Restore cascade deletion of activity tied to a story."""
    op.drop_constraint(
        "activity_events_work_item_id_fkey",
        "activity_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "activity_events_work_item_id_fkey",
        "activity_events",
        "work_items",
        ["work_item_id"],
        ["id"],
        ondelete="CASCADE",
    )

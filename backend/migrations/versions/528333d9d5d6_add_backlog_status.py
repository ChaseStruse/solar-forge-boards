"""add backlog status

Revision ID: 528333d9d5d6
Revises: ed6678dffaac
Create Date: 2026-09-15 21:11:41.829352
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "528333d9d5d6"
down_revision: str | Sequence[str] | None = "ed6678dffaac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow stories to move into the hidden backlog lane."""
    op.drop_constraint("ck_work_items_status", "work_items", type_="check")
    op.create_check_constraint(
        "ck_work_items_status",
        "work_items",
        "status IN ('backlog', 'todo', 'in_progress', 'blocked', 'done', 'cancelled')",
    )


def downgrade() -> None:
    """Restore the prior status set after rejecting populated backlog rows."""
    connection = op.get_bind()
    backlog_count = connection.execute(
        sa.text("SELECT count(*) FROM work_items WHERE status = 'backlog'")
    ).scalar_one()
    if backlog_count:
        raise RuntimeError("Cannot remove backlog status while backlog stories exist.")
    op.drop_constraint("ck_work_items_status", "work_items", type_="check")
    op.create_check_constraint(
        "ck_work_items_status",
        "work_items",
        "status IN ('todo', 'in_progress', 'blocked', 'done', 'cancelled')",
    )

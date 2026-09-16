"""add story points

Revision ID: ed6678dffaac
Revises: 4e8837ce388a
Create Date: 2026-09-15 20:59:00.430108
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ed6678dffaac"
down_revision: str | Sequence[str] | None = "4e8837ce388a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional validated estimates without changing existing stories."""
    op.add_column("work_items", sa.Column("points", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_work_items_points",
        "work_items",
        "points IS NULL OR points IN (1, 3, 5, 8, 13)",
    )


def downgrade() -> None:
    """Remove story estimates while preserving every story row."""
    op.drop_constraint("ck_work_items_points", "work_items", type_="check")
    op.drop_column("work_items", "points")

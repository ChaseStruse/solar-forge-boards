"""Add reversible project archiving and story acceptance criteria.

Revision ID: 20260904_0005
Revises: 20260904_0004
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0005"
down_revision: str | Sequence[str] | None = "20260904_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve existing data while adding the new planning fields."""
    op.add_column("projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "work_items",
        sa.Column("acceptance_criteria", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    """Remove the planning fields added by this revision."""
    op.drop_column("work_items", "acceptance_criteria")
    op.drop_column("projects", "archived_at")

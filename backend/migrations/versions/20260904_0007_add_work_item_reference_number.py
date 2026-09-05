"""Add global human-friendly work-item reference numbers.

Revision ID: 20260904_0007
Revises: 20260904_0006
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0007"
down_revision: str | Sequence[str] | None = "20260904_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill a stable, globally unique number for every existing story."""
    op.add_column("work_items", sa.Column("reference_number", sa.Integer(), nullable=True))
    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS reference_number
            FROM work_items
        )
        UPDATE work_items
        SET reference_number = numbered.reference_number
        FROM numbered
        WHERE work_items.id = numbered.id
        """
    )
    op.alter_column("work_items", "reference_number", nullable=False)
    op.create_unique_constraint(
        "uq_work_items_reference_number", "work_items", ["reference_number"]
    )


def downgrade() -> None:
    """Remove human-friendly story reference numbers."""
    op.drop_constraint("uq_work_items_reference_number", "work_items", type_="unique")
    op.drop_column("work_items", "reference_number")

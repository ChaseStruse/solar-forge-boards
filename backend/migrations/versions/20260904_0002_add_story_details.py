"""Add structured story detail fields without replacing existing data.

Revision ID: 20260904_0002
Revises: 20260903_0001
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0002"
down_revision: str | Sequence[str] | None = "20260903_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional story details with safe defaults for existing rows."""
    op.add_column(
        "work_items",
        sa.Column("technical_description", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "work_items",
        sa.Column("repository_url", sa.String(length=2048), server_default="", nullable=False),
    )


def downgrade() -> None:
    """Remove the structured story detail fields."""
    op.drop_column("work_items", "repository_url")
    op.drop_column("work_items", "technical_description")

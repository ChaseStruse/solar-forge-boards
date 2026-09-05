"""add project repository links

Revision ID: 923c2fb8b1fc
Revises: 20260905_0009
Create Date: 2026-09-05 14:30:21.676614
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "923c2fb8b1fc"
down_revision: str | Sequence[str] | None = "20260905_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects", sa.Column("repository_urls", sa.JSON(), server_default="[]", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("projects", "repository_urls")

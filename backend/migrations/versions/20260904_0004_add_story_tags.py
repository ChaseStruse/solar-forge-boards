"""Add project-scoped story tags and seed the initial taxonomy.

Revision ID: 20260904_0004
Revises: 20260904_0003
Create Date: 2026-09-04
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0004"
down_revision: str | Sequence[str] | None = "20260904_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TAGS: tuple[tuple[str, str], ...] = (
    ("Business", "#ff5fa2"),
    ("Coding", "#63f5c4"),
    ("Configuration", "#6aa9ff"),
    ("Spike", "#aa7cff"),
)


def upgrade() -> None:
    """Create tag tables and give every existing project the default tags."""
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_tags_project_name"),
    )
    op.create_index("ix_tags_project", "tags", ["project_id"])
    op.create_table(
        "work_item_tags",
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("work_item_id", "tag_id"),
    )
    op.create_index("ix_work_item_tags_tag", "work_item_tags", ["tag_id"])

    connection = op.get_bind()
    project_ids = connection.execute(sa.text("SELECT id FROM projects")).scalars().all()
    tag_table = sa.table(
        "tags",
        sa.column("id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("color", sa.String()),
    )
    if project_ids:
        op.bulk_insert(
            tag_table,
            [
                {"id": uuid4(), "project_id": project_id, "name": name, "color": color}
                for project_id in project_ids
                for name, color in DEFAULT_TAGS
            ],
        )


def downgrade() -> None:
    """Remove tag assignments and project tags."""
    op.drop_index("ix_work_item_tags_tag", table_name="work_item_tags")
    op.drop_table("work_item_tags")
    op.drop_index("ix_tags_project", table_name="tags")
    op.drop_table("tags")

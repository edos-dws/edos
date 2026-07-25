"""project_items.domain tag + coverage_answers table (UI-CP-2 coverage engine)

Revision ID: 0008_project_item_domain
Revises: 0007_users_project_owner
Create Date: 2026-07-25
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_project_item_domain"
down_revision = "0007_users_project_owner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_items", sa.Column("domain", sa.String(), nullable=True))
    op.create_index("ix_project_items_domain", "project_items", ["domain"])
    op.create_table(
        "coverage_answers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(), index=True, nullable=False),
        sa.Column("domain", sa.String(), index=True, nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("coverage_answers")
    op.drop_index("ix_project_items_domain", table_name="project_items")
    op.drop_column("project_items", "domain")

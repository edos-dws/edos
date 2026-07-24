"""users table + projects.owner_id (CP-19 auth & multi-tenancy)

Revision ID: 0007_users_project_owner
Revises: 0006_decision_outcomes
Create Date: 2026-07-24
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_users_project_owner"
down_revision = "0006_decision_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("token", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("projects", sa.Column("owner_id", sa.String(), nullable=True))
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_column("projects", "owner_id")
    op.drop_table("users")

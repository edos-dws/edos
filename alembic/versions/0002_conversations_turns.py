"""conversations + turns (CP-10 — project & conversation model)

Revision ID: 0002_conversations_turns
Revises: 0001_initial
Create Date: 2026-07-24

Adds the `conversations` and `turns` tables that let a user chat within a project. Incremental (op.create_table)
so existing deployments upgrade cleanly on top of 0001.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_conversations_turns"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), index=True, nullable=False),
        sa.Column("title", sa.String(), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "turns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.String(), index=True, nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), server_default="", nullable=False),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("turns")
    op.drop_table("conversations")

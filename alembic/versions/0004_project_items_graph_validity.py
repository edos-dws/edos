"""project_items node table + graph_edges.validity (CP-12)

Revision ID: 0004_project_items_graph_validity
Revises: 0003_decision_body_json
Create Date: 2026-07-24
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_project_items_graph_validity"
down_revision = "0003_decision_body_json"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), index=True, nullable=False),
        sa.Column("item_type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("validity", sa.String(), server_default="active", nullable=False),
        sa.Column("needs_linking", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "graph_edges", sa.Column("validity", sa.String(), server_default="active", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("graph_edges", "validity")
    op.drop_table("project_items")

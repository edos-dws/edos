"""assumption_resolutions table (CP-15 interactive resolution)

Revision ID: 0005_assumption_resolutions
Revises: 0004_project_items_graph_validity
Create Date: 2026-07-24
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_assumption_resolutions"
down_revision = "0004_project_items_graph_validity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assumption_resolutions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(), index=True, nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("assumption_resolutions")

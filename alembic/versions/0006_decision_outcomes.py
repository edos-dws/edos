"""decision_outcomes table (CP-17 feedback / learning loop)

Revision ID: 0006_decision_outcomes
Revises: 0005_assumption_resolutions
Create Date: 2026-07-24
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_decision_outcomes"
down_revision = "0005_assumption_resolutions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("decision_id", sa.String(), index=True, nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("confidence_at_outcome", sa.Float(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("decision_outcomes")

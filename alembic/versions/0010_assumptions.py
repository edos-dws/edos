"""assumptions — first-class assumptions + lifecycle (UI-CP-6)

Promotes a decision's inline ``assumptions[]`` (locked contract untouched) to persistent rows with a stable
per-project id ``A{n}`` and a lifecycle status (``created → validated → challenged → invalidated``). The
per-project id is not globally unique, so the primary key is a surrogate ``row_id`` and ``(project_id, id)``
is unique. Incremental (``op.create_table``) so existing deployments upgrade cleanly on top of 0009.

Revision ID: 0010_assumptions
Revises: 0009_decision_detail
Create Date: 2026-07-25
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_assumptions"
down_revision = "0009_decision_detail"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assumptions",
        sa.Column("row_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(), index=True, nullable=False),
        sa.Column("project_id", sa.String(), index=True, nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default="created", nullable=False),
        sa.Column("source_decision_id", sa.String(), index=True, nullable=True),
        sa.Column("risk_if_wrong", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("project_id", "id", name="uq_assumption_project_aid"),
    )


def downgrade() -> None:
    op.drop_table("assumptions")

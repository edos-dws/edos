"""decisions.decision_detail — rich Decision-Card envelope block (UI-CP-4)

The rich Decision-Card fields (comparison_matrix / decision_impact / impacted_components /
review_conditions, …) live in the persistence ENVELOPE, NOT the locked `edos.decision.v1` contract
(same stance as version/supersedes). Stored as JSON alongside the decision on `decisions`.

Revision ID: 0009_decision_detail
Revises: 0008_project_item_domain
Create Date: 2026-07-25
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_decision_detail"
down_revision = "0008_project_item_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("decision_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("decisions", "decision_detail")

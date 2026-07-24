"""decisions.body_json — store full decision contract (CP-11 persistence)

Revision ID: 0003_decision_body_json
Revises: 0002_conversations_turns
Create Date: 2026-07-24

Adds `body_json` to `decisions` to hold the full `edos.decision.v1` contract (source of truth); the existing
projected columns remain for querying/history.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_decision_body_json"
down_revision = "0002_conversations_turns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("body_json", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("decisions", "body_json")

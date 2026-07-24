"""Schema bootstrap (roadmap Ch 11/13).

Deployments use **Alembic** migrations (`alembic upgrade head`; see `alembic/versions/`). `create_all` here
is kept for fast, ephemeral test setup and local bootstrap — not for production schema evolution.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from edos.db import models  # noqa: F401 — ensure tables register on Base.metadata
from edos.db.base import Base


def ensure_pgvector(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def create_all(engine: Engine) -> None:
    ensure_pgvector(engine)
    Base.metadata.create_all(engine)


def drop_all(engine: Engine) -> None:
    Base.metadata.drop_all(engine)

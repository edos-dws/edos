"""Schema bootstrap (roadmap Ch 11/13).

CP-1 uses create_all against a Postgres with pgvector. Formal Alembic migrations are a deferred follow-up
(flagged in CP-1-REPORT.md).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from edos.db.base import Base
from edos.db import models  # noqa: F401 — ensure tables register on Base.metadata


def ensure_pgvector(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def create_all(engine: Engine) -> None:
    ensure_pgvector(engine)
    Base.metadata.create_all(engine)


def drop_all(engine: Engine) -> None:
    Base.metadata.drop_all(engine)

"""Shared DB fixtures. DB tests SKIP (not fail) when Postgres is unreachable, so the suite stays green
without infra; CI provides a pgvector service so they actually run there."""
import os

import pytest
from sqlalchemy import text

from edos.db.base import make_engine, make_session_factory
from edos.db.schema import create_all, drop_all

DB_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://edos:edos@localhost:5432/edos")


@pytest.fixture(scope="session")
def engine():
    eng = make_engine(DB_URL)
    try:
        with eng.connect() as conn:
            conn.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001 — any connect failure => skip DB tests
        pytest.skip(f"Postgres not reachable ({exc.__class__.__name__}); skipping DB tests")
    return eng


@pytest.fixture()
def session(engine):
    drop_all(engine)
    create_all(engine)
    factory = make_session_factory(engine)
    sess = factory()
    try:
        yield sess
    finally:
        sess.close()
        drop_all(engine)

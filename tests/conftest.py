"""Shared DB fixtures. DB tests SKIP (not fail) when Postgres is unreachable, so the suite stays green
without infra; CI provides a pgvector service so they actually run there.

SAFETY: the DB fixtures are **destructive** (`drop_all` in setup and teardown). They must NEVER run against a
real/dev database. So the suite defaults to a dedicated ``edos_test`` database (auto-created), and a guard
refuses to run against any database whose name doesn't look like a test DB unless you explicitly opt in with
``EDOS_ALLOW_DESTRUCTIVE_DB=1``. (This guard exists because the old default pointed at the dev ``edos`` DB and
a full run wiped it.)"""
import os

# Force the offline stubs for the whole suite BEFORE any edos import reads config. This guarantees the gate
# never touches a live model, even on a dev machine that has real keys in `.env` / the shell. Without this,
# once Postgres is up the DB tests ingest/embed through the live Gemini embedder and fail on 429 quota — the
# suite must be hermetic (no infra, no live keys, deterministic), so the reasoning provider AND the
# embedder/reranker/query-expansion all resolve to their stubs here.
os.environ["EDOS_PROVIDER"] = "stub"
os.environ["EDOS_EMBEDDER"] = "stub"
os.environ["EDOS_RERANKER"] = "noop"
os.environ["EDOS_QUERY_EXPANSION"] = "noop"

import pytest
from sqlalchemy import text

from edos.db.base import make_engine, make_session_factory
from edos.db.schema import create_all, drop_all

def _db_name(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?")[0]


def _looks_like_test_db(name: str) -> bool:
    return "test" in name.lower()


def _to_test_db(url: str) -> str:
    """Never let the destructive fixtures touch a non-test database: if the target DB name doesn't look like a
    test DB, redirect to a ``<name>_test`` sibling (which we auto-create). This makes DB tests RUN safely
    instead of either skipping or — as happened once — wiping the dev DB."""
    name = _db_name(url)
    if _looks_like_test_db(name):
        return url
    base = url.rsplit("/", 1)[0]
    return f"{base}/{name}_test"


# Resolve the target: an explicit DATABASE_URL is honoured but redirected to a *_test sibling if it isn't
# already a test DB; unset defaults to the dedicated edos_test database.
DB_URL = _to_test_db(os.environ.get("DATABASE_URL", "postgresql+psycopg://edos:edos@localhost:5432/edos"))


def _ensure_test_db(url: str) -> None:
    """Create the target database (and the pgvector extension) if missing, using the dev ``edos`` DB as the
    maintenance connection. Best-effort: on any failure the caller's connect will fail and the tests skip."""
    name = _db_name(url)
    base = url.rsplit("/", 1)[0]
    admin = make_engine(base + "/edos")
    try:
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if not conn.execute(text("select 1 from pg_database where datname=:n"), {"n": name}).scalar():
                conn.execute(text(f'create database "{name}"'))
    finally:
        admin.dispose()
    tgt = make_engine(url)
    try:
        with tgt.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("create extension if not exists vector"))
    finally:
        tgt.dispose()


@pytest.fixture(scope="session")
def engine():
    # Defense-in-depth: the fixtures run drop_all — refuse outright if the resolved DB isn't a test DB.
    assert _looks_like_test_db(_db_name(DB_URL)), f"destructive fixtures require a *_test DB, got {DB_URL!r}"
    try:
        _ensure_test_db(DB_URL)
        eng = make_engine(DB_URL)
        with eng.connect() as conn:
            conn.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001 — any connect/create failure => skip DB tests
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

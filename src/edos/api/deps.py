"""FastAPI dependencies — the request-scoped DB session (CP-10).

A single module-level engine + session factory is created lazily on first use so importing the app never
requires a live database (tests that don't touch DB stay green). `get_session` is a FastAPI dependency that
yields a session and commits on success / rolls back on error.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from edos.db.base import make_engine, make_session_factory

_engine: Engine | None = None
_factory: sessionmaker | None = None


def session_factory() -> sessionmaker:
    global _engine, _factory
    if _factory is None:
        _engine = make_engine()
        _factory = make_session_factory(_engine)
    return _factory


def get_session() -> Iterator[Session]:
    factory = session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

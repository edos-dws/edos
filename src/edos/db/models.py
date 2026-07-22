"""ORM tables (roadmap Ch 13).

Design invariants:
- **Decisions are immutable + versioned.** Never UPDATE a decision row; append a new version via
  `new_decision_version()`. History is preserved (Ch 3 principle 8).
- Graph edges are dependencies, not similarity (Ch 3).
- Document chunks carry a pgvector embedding for semantic retrieval (Ch 11).

NOTE (CP-1 scope): tables are created via `create_all` (see `schema.py`). Formal Alembic migrations are a
deferred follow-up — flagged in `CP-1-REPORT.md`, not silently skipped.
"""
from __future__ import annotations

import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from edos.db.base import Base

# Placeholder embedding dimension for CP-1. Real dimension is set when the embedding model is chosen
# (CP-2/CP-3). Flagged in CP-1-REPORT.md.
EMBED_DIM = 8


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)


class DecisionRecord(Base):
    """One row per decision *version*. `id` is the stable logical id shared across versions."""

    __tablename__ = "decisions"
    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    rationale: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="proposed")
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    relation_type: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)


def new_decision_version(session: Session, current: DecisionRecord, **changes) -> DecisionRecord:
    """Append a new immutable version of a decision. The current row is left untouched."""
    nxt = DecisionRecord(
        id=current.id,
        project_id=current.project_id,
        title=changes.get("title", current.title),
        rationale=changes.get("rationale", current.rationale),
        confidence=changes.get("confidence", current.confidence),
        status=changes.get("status", current.status),
        version=current.version + 1,
        parent_version=current.version,
    )
    session.add(nxt)
    session.flush()
    return nxt

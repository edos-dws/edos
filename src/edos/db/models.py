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
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
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


class ConversationRow(Base):
    """A chat thread scoped to a project (CP-10). Every analyze runs within a conversation, whose
    project_id anchors downstream retrieval to the right project state."""

    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TurnRow(Base):
    """One prompt+response exchange within a conversation (CP-10). `response_json` stores the raw
    response body; `decision_id` links to a persisted decision once decisions are stored (CP-11)."""

    __tablename__ = "turns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    prompt: Mapped[str] = mapped_column(Text)
    response_json: Mapped[str] = mapped_column(Text, default="")
    decision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    # Full decision contract (edos.decision.v1) as JSON. The projected columns above (title/rationale/
    # confidence/status) are for querying; body_json is the source of truth for the rich decision.
    body_json: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProjectItem(Base):
    """A project knowledge node (CP-12): requirement/decision/assumption/document. These are the graph
    nodes that edges connect and that retrieval scores. `validity` gives temporal "trust now" state;
    `needs_linking` flags an item that entered with no relation (soft, not a silent orphan)."""

    __tablename__ = "project_items"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    item_type: Mapped[str] = mapped_column(String)  # requirement|decision|assumption|document
    content: Mapped[str] = mapped_column(Text)
    validity: Mapped[str] = mapped_column(String, default="active")  # active|superseded|stale|conflicted
    needs_linking: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AssumptionResolution(Base):
    """Records an engineer resolving a decision's assumption (CP-15). Stored separately so the locked
    decision contract stays pure; the resolution triggers a new decision version."""

    __tablename__ = "assumption_resolutions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
    statement: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    relation_type: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    validity: Mapped[str] = mapped_column(String, default="active")  # active|superseded|stale|conflicted


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
        body_json=changes.get("body_json", current.body_json),
    )
    session.add(nxt)
    session.flush()
    return nxt

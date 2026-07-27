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
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from edos.db.base import Base

# Embedding dimension for the pgvector column. 768 = the Matryoshka-truncated size of the Gemini embedding
# models (gemini-embedding-001 / -2 are 3072 natively; truncated to 768 to stay under pgvector's ~2000-dim
# index limit and keep storage/search efficient). The deterministic stub also produces 768-dim vectors.
# Changing this requires a column migration + a re-embed backfill.
EMBED_DIM = 768


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)  # CP-19; null = unowned


class User(Base):
    """Platform user (CP-19). Token-based auth by default; production auth (OAuth/OIDC, hashing) is OD-8."""

    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
    # Rich Decision-Card detail (UI-CP-4): comparison_matrix / decision_impact / impacted_components /
    # review_conditions, etc. as JSON. Kept in the persistence ENVELOPE, NOT the locked decision contract
    # (same stance as version/supersedes) — the core reasoning still emits a contract-valid Decision.
    decision_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # Optional engineering domain tag (UI-CP-2): Architecture|Hardware|Firmware|Manufacturing|Testing|
    # Certification. Feeds the coverage engine; null = untagged (still a valid, retrievable item).
    domain: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Learned usefulness (#7 feedback loop): nudged + when this item fed an ACCEPTED decision, − when it fed a
    # REVERSED one. A small, bounded term in the retrieval rank_score, so the engine self-tunes over time.
    feedback_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CoverageAnswer(Base):
    """A domain question-set answer (UI-CP-2). Persists which question-set questions an engineer has
    answered per project/domain so coverage rises deterministically. The answer's *content* also lands as a
    domain-tagged ProjectItem (so it feeds retrieval); this row just tracks that the question is answered."""

    __tablename__ = "coverage_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    question_id: Mapped[str] = mapped_column(String)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)  # the ProjectItem it was stored as
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DecisionOutcome(Base):
    """Outcome signal for a decision (CP-17): accepted / challenged / reversed. `confidence_at_outcome`
    snapshots the decision's confidence so calibration (predicted vs actual) can be measured over time."""

    __tablename__ = "decision_outcomes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    decision_id: Mapped[str] = mapped_column(String, index=True)
    outcome: Mapped[str] = mapped_column(String)  # accepted | challenged | reversed
    confidence_at_outcome: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class LensFeedback(Base):
    """Learned lens salience (self-tuning weights). `key` is a spine ``axis:value`` token (e.g.
    ``power_source:battery``); `score` accumulates + when a decision of that project-direction is accepted and
    − when reversed, for the lenses that were load-bearing (deep) in that decision. The weighting engine reads
    a bounded sum of these as its learned term, so lens emphasis self-tunes from outcomes on similar-direction
    projects. Additive table — absence just means "nothing learned yet"."""

    __tablename__ = "lens_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, index=True)       # spine "axis:value" token
    lens_id: Mapped[str] = mapped_column(String, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    __table_args__ = (UniqueConstraint("key", "lens_id", name="uq_lens_feedback_key_lens"),)


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


class Assumption(Base):
    """First-class assumption (UI-CP-6). Assumptions are promoted from a decision's INLINE
    ``assumptions[]`` (which stays pure — the locked contract is untouched) to a persistent row with:

    * a **stable per-project id** ``A{n}`` (``id`` — first assumption in a project is ``A1``, next ``A2``…),
      so an assumption can be referenced and can span decisions; and
    * a **lifecycle status** (``created → validated → challenged → invalidated``) so the assumption can be
      tracked, challenged, and fed to decay alerts instead of decaying silently.

    The table MIRRORS the inline contract assumptions with ids + lifecycle; it does not replace them. The
    per-project id is not globally unique (two projects both have an ``A1``), so the primary key is a
    surrogate ``row_id`` and ``(project_id, id)`` is unique."""

    __tablename__ = "assumptions"
    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, index=True)  # A{n} — stable per project (see class docstring)
    project_id: Mapped[str] = mapped_column(String, index=True)
    statement: Mapped[str] = mapped_column(Text)
    # created | validated | challenged | invalidated
    status: Mapped[str] = mapped_column(String, default="created")
    source_decision_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    risk_if_wrong: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    __table_args__ = (UniqueConstraint("project_id", "id", name="uq_assumption_project_aid"),)


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
        decision_detail=changes.get("decision_detail", current.decision_detail),
    )
    session.add(nxt)
    session.flush()
    return nxt

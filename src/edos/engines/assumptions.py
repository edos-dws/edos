"""First-class assumptions + lifecycle (UI-CP-6).

Promotes a decision's INLINE ``assumptions[]`` (which stays pure — the locked ``edos.decision.v1`` contract is
never touched) to persistent :class:`~edos.db.models.Assumption` rows. Each row gets a **stable per-project id**
``A{n}`` and a **lifecycle status** (``created → validated → challenged → invalidated``), so assumptions persist,
carry ids, can span decisions, and can be tracked/challenged instead of decaying silently.

Responsibilities (one engine, one job — CLAUDE.md):
  * ``create`` — assign the next ``A{n}`` for the project, dedupe on statement (case-insensitive) per project.
  * ``upsert_from_decision`` — mirror a decision's inline assumptions into the table on persist.
  * ``list_for_project`` / ``get`` / ``get_by_aid`` — read.
  * ``set_status`` / ``set_status_by_statement`` — lifecycle transitions (used by the resolution engine and
    the status endpoint).

This engine holds no reasoning; it just maintains the assumption ledger. The inline contract assumptions are
the source; these rows mirror them with ids + lifecycle.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import Assumption

STATUSES: tuple[str, ...] = ("created", "validated", "challenged", "invalidated")


def _norm(statement: str) -> str:
    return (statement or "").strip().lower()


def _next_aid(session: Session, project_id: str) -> str:
    """Compute the next ``A{n}`` for a project (max existing n + 1; first is ``A1``)."""
    ids = session.scalars(select(Assumption.id).where(Assumption.project_id == project_id)).all()
    highest = 0
    for aid in ids:
        if aid and aid[0] in ("A", "a") and aid[1:].isdigit():
            highest = max(highest, int(aid[1:]))
    return f"A{highest + 1}"


def list_for_project(session: Session, project_id: str) -> list[Assumption]:
    return list(
        session.scalars(
            select(Assumption).where(Assumption.project_id == project_id).order_by(Assumption.row_id)
        )
    )


def get(session: Session, project_id: str, aid: str) -> Assumption | None:
    return session.scalars(
        select(Assumption).where(Assumption.project_id == project_id, Assumption.id == aid)
    ).first()


def get_by_aid(session: Session, aid: str, project_id: str | None = None) -> Assumption | None:
    """Look up an assumption by its ``A{n}`` id. ``project_id`` disambiguates when the same ``A{n}`` exists in
    more than one project (per-project ids are not globally unique)."""
    stmt = select(Assumption).where(Assumption.id == aid)
    if project_id is not None:
        stmt = stmt.where(Assumption.project_id == project_id)
    return session.scalars(stmt.order_by(Assumption.row_id)).first()


def _find_by_statement(session: Session, project_id: str, statement: str) -> Assumption | None:
    target = _norm(statement)
    if not target:
        return None
    for a in list_for_project(session, project_id):
        if _norm(a.statement) == target:
            return a
    return None


def create(
    session: Session,
    project_id: str,
    statement: str,
    *,
    source_decision_id: str | None = None,
    risk_if_wrong: str | None = None,
    status: str = "created",
) -> Assumption | None:
    """Create (or return the existing) assumption for ``statement`` in ``project_id``.

    Dedupes on statement (case-insensitive) per project so the same assumption stated across decisions maps to
    one row (cross-decision). On a dedupe hit, backfills a missing ``source_decision_id`` / ``risk_if_wrong``
    but never regresses an already-advanced lifecycle status."""
    statement = (statement or "").strip()
    if not statement:
        return None
    existing = _find_by_statement(session, project_id, statement)
    if existing is not None:
        if source_decision_id and not existing.source_decision_id:
            existing.source_decision_id = source_decision_id
        if risk_if_wrong and not existing.risk_if_wrong:
            existing.risk_if_wrong = risk_if_wrong
        session.flush()
        return existing
    if status not in STATUSES:
        status = "created"
    row = Assumption(
        id=_next_aid(session, project_id),
        project_id=project_id,
        statement=statement,
        status=status,
        source_decision_id=source_decision_id,
        risk_if_wrong=risk_if_wrong,
    )
    session.add(row)
    session.flush()
    return row


def upsert_from_decision(session: Session, project_id: str, decision, source_decision_id: str) -> list[Assumption]:
    """Mirror a decision's inline ``assumptions[]`` into the Assumption table (status ``created``).

    Called when a decision is persisted (``POST /v1/decisions`` and Deep Dive decide). The inline contract
    assumptions are left untouched; each is upserted (deduped per project) as a first-class row."""
    created: list[Assumption] = []
    for a in getattr(decision, "assumptions", []) or []:
        row = create(
            session,
            project_id,
            a.statement,
            source_decision_id=source_decision_id,
            risk_if_wrong=getattr(a, "risk_if_wrong", None),
        )
        if row is not None:
            created.append(row)
    return created


def set_status(
    session: Session, *, aid: str, status: str, project_id: str | None = None
) -> Assumption | None:
    """Transition an assumption (by ``A{n}`` id) to a new lifecycle status. Returns None if not found."""
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status!r} (expected one of {STATUSES})")
    row = get_by_aid(session, aid, project_id)
    if row is None:
        return None
    row.status = status
    session.flush()
    return row


def set_status_by_statement(
    session: Session, project_id: str, statement: str, status: str
) -> Assumption | None:
    """Transition the assumption matching ``statement`` (case-insensitive) in a project. No-op (returns None)
    if there is no matching first-class assumption — used to keep the table in step with the resolution engine
    without failing when a statement was never promoted."""
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status!r} (expected one of {STATUSES})")
    row = _find_by_statement(session, project_id, statement)
    if row is None:
        return None
    row.status = status
    session.flush()
    return row

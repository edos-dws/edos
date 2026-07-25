"""Research Workspace — sources referenced (UI-CP-10, PDF p7).

The datasheets / sources a decision (or a whole project) is grounded in. Two ingredients, both already
persisted — nothing here is fabricated:

  * **Document items** — ``ProjectItem`` rows with ``item_type == 'document'`` in the project (datasheets /
    sources attached via the coverage/attach flow, PDF "referenced by DR-001").
  * **Evidence sources** — the ``evidence[].source`` entries inside a decision's locked contract body (the
    claims-and-their-sources the reasoning already cites).

Deterministic read-only projection; one responsibility (CLAUDE.md).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import ProjectItem
from edos.engines import decision_store


def _document_items(session: Session, project_id: str) -> list[dict]:
    rows = session.scalars(
        select(ProjectItem)
        .where(ProjectItem.project_id == project_id, ProjectItem.item_type == "document")
        .order_by(ProjectItem.created_at)
    )
    return [
        {
            "id": it.id, "content": it.content, "domain": it.domain, "validity": it.validity,
            "created_at": it.created_at.isoformat() if it.created_at else None,
        }
        for it in rows
    ]


def _evidence_of(row) -> list[dict]:
    """De-duped ``evidence[]`` entries (claim / source / kind) from a decision's contract body."""
    dec = decision_store.to_decision(row)
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for ev in dec.evidence:
        key = (ev.claim, ev.source)
        if key in seen:
            continue
        seen.add(key)
        out.append({"claim": ev.claim, "source": ev.source, "kind": ev.kind})
    return out


def for_decision(session: Session, decision_id: str) -> dict | None:
    """Research Workspace for one decision: the project's document items + this decision's evidence sources.
    Returns None if the decision does not exist (endpoint → 404)."""
    row = decision_store.get_latest(session, decision_id)
    if row is None:
        return None
    return {
        "decision_id": decision_id,
        "project_id": row.project_id,
        "documents": _document_items(session, row.project_id),
        "evidence": _evidence_of(row),
    }


def for_project(session: Session, project_id: str) -> dict:
    """Research Workspace for a whole project: all document items + the union of evidence sources across the
    project's latest-version decisions."""
    evidence: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in decision_store.list_for_project(session, project_id):
        for ev in _evidence_of(row):
            key = (ev["claim"], ev["source"])
            if key in seen:
                continue
            seen.add(key)
            evidence.append({**ev, "decision_id": row.id})
    return {
        "project_id": project_id,
        "documents": _document_items(session, project_id),
        "evidence": evidence,
    }

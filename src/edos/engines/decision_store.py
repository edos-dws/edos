"""Decision persistence (CP-11) — immutable, versioned decision records.

Bridges the reasoning contract (`Decision`, `edos.decision.v1`) and its DB projection (`DecisionRecord`).
The full contract is stored in `body_json` (source of truth); projected columns (title/rationale/confidence/
status/version) exist for querying and history.

Invariant (CLAUDE.md): decisions are **never mutated in place** — every change appends a new version via
`new_decision_version()`, leaving prior versions intact for audit.

Note: version/supersedes/project_id are persistence-envelope metadata kept here, NOT added to the locked
`decision.schema.json` — the reasoning contract stays pure. Cross-decision supersession lives in the graph
(`supersedes` / `conflicts_with` edges, CP-12), not in this contract.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import DecisionRecord, new_decision_version
from edos.models.decision import Decision


def _project(decision: Decision) -> dict:
    return {
        "title": decision.summary,
        "rationale": decision.recommendation,
        "confidence": decision.confidence,
        "status": decision.status,
        "body_json": json.dumps(decision.to_contract_dict()),
    }


def save_new(
    session: Session, *, id: str, project_id: str, decision: Decision, status: str | None = None,
    detail: dict | None = None,
) -> DecisionRecord:
    """Persist a brand-new decision as version 1.

    `detail` is the optional rich Decision-Card block (UI-CP-4): comparison_matrix / decision_impact /
    impacted_components / review_conditions, etc. It is stored in the persistence envelope
    (`decision_detail` column), NOT inside the locked `edos.decision.v1` contract."""
    fields = _project(decision)
    if status is not None:
        fields["status"] = status
    if detail is not None:
        fields["decision_detail"] = json.dumps(detail)
    row = DecisionRecord(id=id, project_id=project_id, version=1, parent_version=None, **fields)
    session.add(row)
    session.flush()
    return row


def get_latest(session: Session, decision_id: str) -> DecisionRecord | None:
    return session.scalars(
        select(DecisionRecord)
        .where(DecisionRecord.id == decision_id)
        .order_by(DecisionRecord.version.desc())
    ).first()


def get_version(session: Session, decision_id: str, version: int) -> DecisionRecord | None:
    return session.scalars(
        select(DecisionRecord)
        .where(DecisionRecord.id == decision_id, DecisionRecord.version == version)
    ).first()


def history(session: Session, decision_id: str) -> list[DecisionRecord]:
    return list(
        session.scalars(
            select(DecisionRecord)
            .where(DecisionRecord.id == decision_id)
            .order_by(DecisionRecord.version)
        )
    )


def list_for_project(session: Session, project_id: str) -> list[DecisionRecord]:
    """Latest version per logical decision id in a project."""
    rows = session.scalars(
        select(DecisionRecord)
        .where(DecisionRecord.project_id == project_id)
        .order_by(DecisionRecord.id, DecisionRecord.version.desc())
    ).all()
    latest: dict[str, DecisionRecord] = {}
    for row in rows:
        if row.id not in latest:  # first seen = highest version (desc order)
            latest[row.id] = row
    return list(latest.values())


def accept(session: Session, decision_id: str, *, edited: Decision | None = None) -> DecisionRecord | None:
    """Append a new `accepted` version. `edited` supplies a revised decision; otherwise the current body is
    carried forward. The prior version is left immutable."""
    current = get_latest(session, decision_id)
    if current is None:
        return None
    changes = {"status": "accepted"}
    if edited is not None:
        changes.update(_project(edited))
        changes["status"] = "accepted"
    return new_decision_version(session, current, **changes)


def to_decision(row: DecisionRecord) -> Decision:
    """Reconstruct the rich contract from a stored record."""
    return Decision(**json.loads(row.body_json))

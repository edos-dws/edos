"""Interactive resolution (CP-15) — assumption + conflict resolution close the loop.

Resolving an assumption records the engineer's answer and appends a new decision version (audit-preserving),
clearing any freeze_blocker that named that assumption. Resolving a conflict closes the `conflicts_with`
edges and restores node validity. The full LLM *re-reasoning* on the resolved state is deferred (stub
pattern) — here the deterministic state transition and versioning are complete.
"""
from __future__ import annotations

import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from edos.db.models import (
    AssumptionResolution,
    DecisionRecord,
    GraphEdge,
    ProjectItem,
    new_decision_version,
)
from edos.engines import assumptions as assumptions_engine
from edos.engines import decision_store
from edos.models.decision import Risk
from edos.models.entities import RelationType


def resolve_assumption(
    session: Session, *, decision_id: str, statement: str, resolution: str, resolved_by: str | None = None
) -> DecisionRecord | None:
    """Record the resolution and append a new decision version with the matching freeze_blocker cleared."""
    current = decision_store.get_latest(session, decision_id)
    if current is None:
        return None
    session.add(AssumptionResolution(decision_id=decision_id, statement=statement, resolution=resolution,
                                     resolved_by=resolved_by))
    decision = decision_store.to_decision(current)
    # drop any freeze_blocker that referenced this assumption (now resolved) — legitimate, not fabricated
    kept = [b for b in decision.freeze_blockers if statement.lower() not in b.lower()]
    revised = decision.model_copy(update={"freeze_blockers": kept})
    # keep the first-class assumption ledger in step: resolving validates the matching assumption (UI-CP-6)
    assumptions_engine.set_status_by_statement(session, current.project_id, statement, "validated")
    return new_decision_version(
        session, current, status="accepted", body_json=_dump(revised), rationale=revised.recommendation,
    )


def challenge_assumption(
    session: Session, *, decision_id: str, statement: str, note: str | None = None,
    challenged_by: str | None = None,
) -> DecisionRecord | None:
    """Mark an assumption **challenged** (UI-CP-5): it stops being a silent assumption and becomes a *monitored
    risk*. Same audit-preserving shape as ``resolve_assumption`` — records the transition and appends a new
    decision version — but instead of clearing a freeze_blocker it adds a monitored Risk that names the
    assumption, so the (now-tracked) risk can't decay unnoticed. Idempotent on repeated challenges."""
    current = decision_store.get_latest(session, decision_id)
    if current is None:
        return None
    resolution = "challenged — monitored risk" + (f": {note}" if note else "")
    session.add(AssumptionResolution(decision_id=decision_id, statement=statement, resolution=resolution,
                                     resolved_by=challenged_by))
    decision = decision_store.to_decision(current)
    tag = f"Challenged assumption (monitored): {statement}"
    already = any(r.description == tag for r in decision.risks)
    risks = list(decision.risks)
    if not already:
        matched = next((a for a in decision.assumptions if a.statement.strip().lower() == statement.strip().lower()), None)
        risk_if = (matched.risk_if_wrong if matched and matched.risk_if_wrong
                   else "Was a silent assumption; now tracked so it cannot decay unnoticed.")
        risks.append(Risk(description=tag, severity="medium", likelihood="medium",
                          mitigation=f"Monitored risk — {risk_if} Revisit the decision if this assumption shifts."))
    revised = decision.model_copy(update={"risks": risks})
    # keep the first-class assumption ledger in step: challenging flips the matching assumption (UI-CP-6)
    assumptions_engine.set_status_by_statement(session, current.project_id, statement, "challenged")
    # status is preserved (challenging an assumption does not itself accept/reject the decision)
    return new_decision_version(session, current, body_json=_dump(revised))


def _dump(decision) -> str:
    return json.dumps(decision.to_contract_dict())


def resolutions_for(session: Session, decision_id: str) -> list[AssumptionResolution]:
    return list(session.scalars(
        select(AssumptionResolution).where(AssumptionResolution.decision_id == decision_id)
        .order_by(AssumptionResolution.created_at, AssumptionResolution.id)
    ))


def resolve_conflict(session: Session, *, node_a: str, node_b: str) -> int:
    """Close the conflicts_with edges between two nodes and restore their validity. Returns edges closed."""
    edges = session.scalars(
        select(GraphEdge).where(
            GraphEdge.relation_type == RelationType.conflicts_with.value,
            or_(
                (GraphEdge.source_id == node_a) & (GraphEdge.target_id == node_b),
                (GraphEdge.source_id == node_b) & (GraphEdge.target_id == node_a),
            ),
        )
    ).all()
    for e in edges:
        e.validity = "resolved"
    for nid in (node_a, node_b):
        item = session.get(ProjectItem, nid)
        if item is not None and item.validity == "conflicted":
            item.validity = "active"
    session.flush()
    return len(edges)

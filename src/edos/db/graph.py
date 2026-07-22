"""Decision Graph traversal + relation weights (roadmap Ch 15).

Graph retrieval always precedes vector retrieval (Ch 11). Traversal is deterministic software, never an LLM.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import GraphEdge
from edos.models.entities import RelationType

# Weights documented in roadmap Ch 15.
RELATION_WEIGHTS: dict[RelationType, float] = {
    RelationType.depends_on: 10.0,
    RelationType.influences: 8.0,
    RelationType.invalidates: 7.0,
    RelationType.mitigates: 6.0,
    RelationType.related_to: 3.0,
}
# The other 6 relation types are not weighted in Ch 15. Neutral default pending confirmation at the CP-1
# gate (flagged in CP-1-REPORT.md) — a documented placeholder, NOT an invented authoritative value.
DEFAULT_WEIGHT = 5.0


def weight_for(relation_type: RelationType | str) -> float:
    return RELATION_WEIGHTS.get(RelationType(relation_type), DEFAULT_WEIGHT)


def neighbors(
    session: Session, node_id: str, relation_type: RelationType | str | None = None
) -> list[GraphEdge]:
    """Outgoing edges from `node_id`, optionally filtered to one relation type."""
    q = select(GraphEdge).where(GraphEdge.source_id == node_id)
    if relation_type is not None:
        q = q.where(GraphEdge.relation_type == RelationType(relation_type).value)
    return list(session.scalars(q))

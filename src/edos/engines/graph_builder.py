"""Graph builder (CP-12) — keeps the decision graph connected, consistent, and temporally valid.

Responsibilities (deterministic software, never an LLM here):
- **Edge extraction** from item content by explicit reference to known node ids (implicit/semantic extraction
  is LLM-gated and deferred — see CP-12 report).
- **Integrity**: no dangling edges (target must be a real node), `supersedes` stays acyclic (a DAG),
  `conflicts_with` is symmetric.
- **Temporal validity**: creating `supersedes`/`invalidates`/`conflicts_with` transitions node validity
  (superseded / stale / conflicted) so retrieval can prefer what is trustworthy now.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import DecisionRecord, GraphEdge, ProjectItem
from edos.models.entities import RelationType

# keyword → relation, scanned near a referenced id in content (first match wins)
_KEYWORD_RELATION: list[tuple[str, RelationType]] = [
    ("supersede", RelationType.supersedes),
    ("conflict", RelationType.conflicts_with),
    ("depend", RelationType.depends_on),
    ("mitigat", RelationType.mitigates),
    ("invalidat", RelationType.invalidates),
    ("deriv", RelationType.derived_from),
    ("validat", RelationType.validates),
    ("influenc", RelationType.influences),
    ("relat", RelationType.related_to),
]


class GraphIntegrityError(ValueError):
    """Raised when an edge would violate a graph invariant (dangling / cycle)."""


def node_exists(session: Session, node_id: str) -> bool:
    if session.get(ProjectItem, node_id) is not None:
        return True
    return session.scalars(
        select(DecisionRecord.id).where(DecisionRecord.id == node_id).limit(1)
    ).first() is not None


def extract_edges(content: str, known_ids: list[str]) -> list[tuple[str, RelationType]]:
    """Explicit-reference extraction: for each known id mentioned in `content`, infer the relation from a
    nearby keyword (default `references`)."""
    low = content.lower()
    edges: list[tuple[str, RelationType]] = []
    for tid in known_ids:
        pos = low.find(tid.lower())
        if pos == -1:
            continue
        window = low[max(0, pos - 40):pos]  # words just before the reference
        # choose the keyword NEAREST to the reference (largest position in the window), not list order
        relation = RelationType.references
        best = -1
        for kw, rel in _KEYWORD_RELATION:
            at = window.rfind(kw)
            if at > best:
                best = at
                relation = rel
        edges.append((tid, relation))
    return edges


def _supersedes_path_exists(session: Session, start: str, goal: str) -> bool:
    """Is there a supersedes path start → … → goal? (Used to reject a cycle-closing edge.)"""
    seen: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        targets = session.scalars(
            select(GraphEdge.target_id).where(
                GraphEdge.source_id == node,
                GraphEdge.relation_type == RelationType.supersedes.value,
            )
        ).all()
        stack.extend(targets)
    return False


def _set_validity(session: Session, node_id: str, validity: str) -> None:
    item = session.get(ProjectItem, node_id)
    if item is not None:
        item.validity = validity


def add_edge(
    session: Session, *, source_id: str, target_id: str, relation: RelationType | str,
    confidence: float = 1.0, require_target: bool = True,
) -> GraphEdge:
    """Add an edge with integrity + temporal side-effects. Symmetric for conflicts_with."""
    relation = RelationType(relation)
    if source_id == target_id:
        raise GraphIntegrityError("self-edge not allowed")
    if require_target and not node_exists(session, target_id):
        raise GraphIntegrityError(f"dangling edge: target {target_id!r} is not a node")
    if relation is RelationType.supersedes and _supersedes_path_exists(session, target_id, source_id):
        raise GraphIntegrityError("supersedes cycle rejected (must stay a DAG)")

    edge = GraphEdge(source_id=source_id, target_id=target_id,
                     relation_type=relation.value, confidence=confidence)
    session.add(edge)

    # temporal side-effects
    if relation is RelationType.supersedes:
        _set_validity(session, target_id, "superseded")
    elif relation is RelationType.invalidates:
        _set_validity(session, target_id, "stale")
    elif relation is RelationType.conflicts_with:
        _set_validity(session, source_id, "conflicted")
        _set_validity(session, target_id, "conflicted")
        # symmetric back-edge (idempotent-ish: only if not already present)
        exists = session.scalars(
            select(GraphEdge).where(
                GraphEdge.source_id == target_id, GraphEdge.target_id == source_id,
                GraphEdge.relation_type == RelationType.conflicts_with.value,
            ).limit(1)
        ).first()
        if exists is None:
            session.add(GraphEdge(source_id=target_id, target_id=source_id,
                                  relation_type=RelationType.conflicts_with.value, confidence=confidence))
    session.flush()
    return edge


_REF_TOKEN = re.compile(r"\b(?:REQ|DEC|ASM|CON|D|ITEM)-[A-Za-z0-9]+\b")


def referenced_tokens(content: str) -> list[str]:
    """Explicit id-like tokens in content (for quick reference scanning)."""
    return _REF_TOKEN.findall(content)

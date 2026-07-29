"""Semantic graph edges (A5, Layer 2) — infer relationships that aren't explicitly written.

`graph_builder.extract_edges` (Layer 1) only finds an edge where the content literally names another node id.
Two decisions can contradict without either mentioning the other, and nothing catches it. This Layer 2 fills
that gap: for a newly-ingested item, retrieve its semantic nearest neighbours (real embeddings — the A4
dependency; with stub vectors the candidate set is noise), then a single LLM call classifies the relationship
to each candidate.

Safety by stakes (the critical design):
  * **Low-stakes** relations (`related_to`/`influences`/`depends_on`/`references`/`derived_from`) are applied
    directly — through `graph_builder.add_edge`, which stays the single integrity gatekeeper, tagged
    `origin="semantic"` with the classifier's rationale.
  * **High-stakes** relations (`supersedes`/`invalidates`/`conflicts_with`) change which decisions are
    trustworthy (a false conflict marks two good decisions conflicted and can block a freeze). These are NOT
    auto-applied — they are returned as **suspected** edges for human confirmation (the watchdog UX). Only a
    confirmed one is passed to `add_edge` to run the real validity transition.

Offline / no key / malformed output → returns empty (Layer 1 remains the floor). Flag-gated at the ingest
hook (`EDOS_SEMANTIC_EDGES`).
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from edos.db.models import GraphEdge, ProjectItem
from edos.engines import graph_builder, retrieval
from edos.engines.model_router import Capability, ModelRouter
from edos.models.entities import RelationType

_SUSPECTED = "suspected"  # a high-stakes semantic proposal awaiting human confirm — persisted, NOT applied

# Relations safe to auto-apply vs. those that change node validity and must be human-confirmed.
_LOW_STAKES = {RelationType.related_to, RelationType.influences, RelationType.depends_on,
               RelationType.references, RelationType.derived_from, RelationType.mitigates,
               RelationType.validates}
_HIGH_STAKES = {RelationType.supersedes, RelationType.invalidates, RelationType.conflicts_with}

_CANDIDATE_K = 5
_MIN_CONFIDENCE = 0.6  # placeholder until calibrated against the edge-quality eval (A5 §6); tune for precision

_EDGES_SCHEMA = {
    "type": "object",
    "required": ["edges"],
    "properties": {"edges": {"type": "array", "items": {
        "type": "object",
        "required": ["target_id", "relation"],
        "properties": {
            "target_id": {"type": "string"},
            "relation": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "rationale": {"type": "string"},
        },
    }}},
}


def propose_semantic_edges(
    session: Session,
    project_id: str,
    item_id: str,
    router: ModelRouter | None = None,
    min_confidence: float = _MIN_CONFIDENCE,
) -> dict:
    """Classify the new item against its semantic neighbours. Returns `{applied, suspected}`:
    `applied` = low-stakes edges written through add_edge; `suspected` = high-stakes edges surfaced for
    confirmation (NOT applied). Best-effort — any failure (offline, malformed, integrity) yields no edges."""
    item = session.get(ProjectItem, item_id)
    if item is None or not (item.content or "").strip():
        return {"applied": [], "suspected": []}

    # Candidates: semantic nearest neighbours (excluding self). Best-effort — no candidates → nothing to do.
    try:
        cands = retrieval.retrieve(session, project_id=project_id, question=item.content)
    except Exception:  # noqa: BLE001 — retrieval is best-effort; never block ingest on it
        return {"applied": [], "suspected": []}
    candidates = [{"id": c["ref_id"], "type": c.get("type", ""), "content": c.get("content", "")}
                  for c in cands if c.get("ref_id") and c["ref_id"] != item_id][:_CANDIDATE_K]
    if not candidates:
        return {"applied": [], "suspected": []}

    try:
        raw = (router or ModelRouter()).execute(
            Capability.relationship,
            {"new_item": {"id": item_id, "type": item.item_type, "content": item.content},
             "candidates": candidates},
            schema=_EDGES_SCHEMA,
        )
    except Exception:  # noqa: BLE001 — no live/valid classifier → Layer-1 only
        return {"applied": [], "suspected": []}

    applied: list[dict] = []
    suspected: list[dict] = []
    valid_targets = {c["id"] for c in candidates}
    for e in (raw.get("edges") or []):
        try:
            relation = RelationType(e.get("relation"))
        except (ValueError, TypeError):
            continue  # "none" or an unknown relation → skip
        target = e.get("target_id")
        conf = float(e.get("confidence", 0.0) or 0.0)
        rationale = str(e.get("rationale", "")).strip()
        if target not in valid_targets or conf < min_confidence:
            continue
        record = {"target_id": target, "relation": relation.value, "confidence": conf, "rationale": rationale}
        if relation in _HIGH_STAKES:
            # persist as a SUSPECTED edge (validity="suspected") so it survives ingest and the watchdog/UI can
            # surface it — but do NOT flip node validity (a false conflict must not silently mark two good
            # decisions conflicted or block a freeze). It becomes real only on human confirm.
            _persist_suspected(session, item_id, target, relation.value, conf, rationale)
            suspected.append(record)
            continue
        try:
            graph_builder.add_edge(session, source_id=item_id, target_id=target, relation=relation,
                                   confidence=conf, origin="semantic", rationale=rationale)
            applied.append(record)
        except graph_builder.GraphIntegrityError:
            continue  # add_edge rejected it (dangling/cycle/self) — the gatekeeper holds
    session.flush()
    return {"applied": applied, "suspected": suspected}


# --- suspected (high-stakes semantic) proposals: persist → surface → confirm/dismiss (B2) ----------------

def _edge_between(session: Session, a: str, b: str, relation: str, validities: list[str]):
    """Any edge of `relation` between a and b (either direction) in one of `validities`."""
    return session.scalars(
        select(GraphEdge).where(
            GraphEdge.relation_type == relation,
            GraphEdge.validity.in_(validities),
            or_(
                (GraphEdge.source_id == a) & (GraphEdge.target_id == b),
                (GraphEdge.source_id == b) & (GraphEdge.target_id == a),
            ),
        )
    ).all()


def _persist_suspected(session: Session, source_id: str, target_id: str, relation: str,
                       confidence: float, rationale: str) -> bool:
    """Store a high-stakes proposal as a `suspected` edge. Idempotent: skips if the pair already has this
    relation as `suspected` OR already `active` (no point suspecting what is already confirmed)."""
    if _edge_between(session, source_id, target_id, relation, [_SUSPECTED, "active"]):
        return False
    session.add(GraphEdge(source_id=source_id, target_id=target_id, relation_type=relation,
                          confidence=confidence, origin="semantic", rationale=rationale, validity=_SUSPECTED))
    session.flush()
    return True


def list_suspected(session: Session, project_id: str) -> list[dict]:
    """The project's suspected (semantic, unconfirmed) high-stakes edges — awaiting confirm/dismiss."""
    item_ids = set(session.scalars(select(ProjectItem.id).where(ProjectItem.project_id == project_id)))
    if not item_ids:
        return []
    rels = [r.value for r in _HIGH_STAKES]
    edges = session.scalars(
        select(GraphEdge).where(GraphEdge.relation_type.in_(rels), GraphEdge.validity == _SUSPECTED)
    ).all()
    return [
        {"source_id": e.source_id, "target_id": e.target_id, "relation": e.relation_type,
         "confidence": e.confidence, "rationale": e.rationale}
        for e in edges if e.source_id in item_ids or e.target_id in item_ids
    ]


def confirm_suspected(session: Session, source_id: str, target_id: str, relation: str) -> dict:
    """Promote a suspected edge to a real one: remove the suspected record and re-add through the single
    integrity gatekeeper (`graph_builder.add_edge`), which applies the temporal side-effects (conflicts_with
    → both nodes `conflicted` + symmetric back-edge; supersedes/invalidates → target superseded/stale). This
    is the ONLY path a semantic high-stakes proposal changes node validity."""
    try:
        rel = RelationType(relation)
    except (ValueError, TypeError):
        return {"confirmed": False, "reason": f"unknown relation {relation!r}"}
    edges = _edge_between(session, source_id, target_id, rel.value, [_SUSPECTED])
    if not edges:
        return {"confirmed": False, "reason": "no suspected edge for that pair/relation"}
    src, tgt = edges[0].source_id, edges[0].target_id  # preserve the proposal's direction
    conf, rationale = edges[0].confidence, edges[0].rationale
    for e in edges:
        session.delete(e)
    session.flush()
    try:
        graph_builder.add_edge(session, source_id=src, target_id=tgt, relation=rel,
                               confidence=conf, origin="semantic", rationale=rationale)
    except graph_builder.GraphIntegrityError as exc:
        return {"confirmed": False, "reason": str(exc)}
    return {"confirmed": True, "source_id": src, "target_id": tgt, "relation": rel.value}


def dismiss_suspected(session: Session, source_id: str, target_id: str, relation: str) -> dict:
    """Reject a suspected edge: mark it `dismissed` (kept for audit, never applied, never re-surfaced)."""
    try:
        rel = RelationType(relation)
    except (ValueError, TypeError):
        return {"dismissed": 0, "reason": f"unknown relation {relation!r}"}
    edges = _edge_between(session, source_id, target_id, rel.value, [_SUSPECTED])
    for e in edges:
        e.validity = "dismissed"
    session.flush()
    return {"dismissed": len(edges)}

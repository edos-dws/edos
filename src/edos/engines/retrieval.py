"""Retriever (CP-13) — assembles a project's relevant context for reasoning.

"The LLM never searches the project. The Retriever does." Deterministic hybrid retrieval:
anchor extraction → dense (pgvector cosine kNN) + lexical (term overlap) + graph traversal/expansion +
recency → per-candidate signals → weighted `rank_score` (via the Context Engine). A **hard-constraint floor**
keeps must-see items (active requirements, open conflicts); a **missing-context guard** flags thin coverage
instead of reasoning blind. Temporal validity feeds the confidence signal so stale/superseded items rank down.

LLM-gated and deferred (same stub pattern as CP-12): anchor LLM-fallback, cross-encoder/LLM rerank, and
agentic multi-hop. The deterministic pipeline here is the source of truth for retrieval quality (measured by
`eval/retrieval_eval.py`; OD-3 recall@k threshold is data-derived — not fabricated).
"""
from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from edos.db.graph import weight_for
from edos.db.models import DocumentChunk, GraphEdge, ProjectItem
from edos.engines import graph_builder
from edos.engines.embeddings import EmbeddingProvider, default_embedder

_VALID_TYPES = {"project", "requirement", "decision", "assumption", "risk", "document", "external"}
# temporal validity → confidence signal ("trust now")
_VALIDITY_CONFIDENCE = {"active": 0.9, "conflicted": 0.5, "stale": 0.3, "superseded": 0.2}
_MAX_EDGE_WEIGHT = 10.0
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _map_type(item_type: str) -> str:
    return item_type if item_type in _VALID_TYPES else "document"


def _validity_confidence(validity: str) -> float:
    return _VALIDITY_CONFIDENCE.get(validity, 0.7)


def _recency_score(created_at: dt.datetime | None, now: dt.datetime, half_life_days: float = 30.0) -> float:
    if created_at is None:
        return 0.5
    age_days = (now - created_at).total_seconds() / 86400.0
    return 0.5 ** (max(age_days, 0.0) / half_life_days)


def _dense_scores(session: Session, project_id: str, qvec: list[float], k: int) -> dict[str, float]:
    rows = session.execute(
        select(
            DocumentChunk.document_id,
            DocumentChunk.embedding.cosine_distance(qvec).label("dist"),
        )
        .where(DocumentChunk.project_id == project_id)
        .order_by("dist")
        .limit(k)
    ).all()
    return {r.document_id: max(0.0, min(1.0, 1.0 - float(r.dist))) for r in rows}


def _lexical_scores(question: str, items: list[ProjectItem]) -> dict[str, float]:
    q = _tokens(question)
    if not q:
        return {}
    out: dict[str, float] = {}
    for it in items:
        overlap = len(q & _tokens(it.content)) / len(q)  # fraction of query terms present
        if overlap > 0:
            out[it.id] = overlap
    return out


def _anchor_ids(items: list[ProjectItem], question: str, dense: dict[str, float]) -> set[str]:
    ids = {it.id for it in items}
    anchors = {t for t in graph_builder.referenced_tokens(question) if t in ids}  # explicit refs
    top = sorted(dense.items(), key=lambda kv: kv[1], reverse=True)[:3]           # semantic anchors
    anchors |= {iid for iid, score in top if score > 0.3}
    return anchors


def _graph_scores(
    session: Session, anchor_ids: set[str], hop_limit: int, decay: float = 0.5
) -> dict[str, float]:
    """Weighted seeded traversal (both directions) from anchors: score = decay^hop × edge-weight, keeping
    the best path to each node. Surfaces connected decisions and conflicts (core purpose)."""
    scores: dict[str, float] = {a: 1.0 for a in anchor_ids}
    frontier: dict[str, float] = dict(scores)
    for _hop in range(hop_limit):
        nxt: dict[str, float] = {}
        for node, base in frontier.items():
            edges = session.scalars(
                select(GraphEdge).where(or_(GraphEdge.source_id == node, GraphEdge.target_id == node))
            ).all()
            for e in edges:
                other = e.target_id if e.source_id == node else e.source_id
                s = base * decay * (weight_for(e.relation_type) / _MAX_EDGE_WEIGHT)
                if s > scores.get(other, 0.0):
                    scores[other] = s
                    nxt[other] = max(nxt.get(other, 0.0), s)
        frontier = nxt
        if not frontier:
            break
    return scores


def _is_hard_constraint(item: ProjectItem) -> bool:
    """Must-see: active requirements (constraints) and any open conflict — never dropped by ranking."""
    if item.validity == "conflicted":
        return True
    return item.item_type == "requirement" and item.validity == "active"


def retrieve(
    session: Session, *, project_id: str, question: str,
    embedder: EmbeddingProvider | None = None, k: int = 50, hop_limit: int = 2,
) -> list[dict]:
    """Return ContextEngine-shaped candidates (`{type, ref_id, content, signals}`) for a project+question."""
    embedder = embedder or default_embedder()
    items = list(session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id)))
    if not items:
        return []

    qvec = embedder.embed(question)
    dense = _dense_scores(session, project_id, qvec, k)
    lexical = _lexical_scores(question, items)
    anchors = _anchor_ids(items, question, dense)
    graphsig = _graph_scores(session, anchors, hop_limit)
    now = dt.datetime.now(dt.UTC)

    candidates: list[dict] = []
    for it in items:
        semantic = max(dense.get(it.id, 0.0), lexical.get(it.id, 0.0))
        # hard-constraint floor: mark must-see items with full focus so ranking/compression keeps them.
        # (Coverage below is measured on *real* semantic/graph, not the floor, so the guard stays honest.)
        focus = 1.0 if (it.id in anchors or _is_hard_constraint(it)) else 0.3
        candidates.append({
            "type": _map_type(it.item_type),
            "ref_id": it.id,
            "content": it.content,
            "signals": {
                "graph": round(graphsig.get(it.id, 0.0), 6),
                "semantic": round(min(semantic, 1.0), 6),
                "recency": round(_recency_score(it.created_at, now), 6),
                "confidence": _validity_confidence(it.validity),
                "focus": focus,
            },
        })
    return candidates


def coverage_ok(candidates: list[dict], threshold: float = 0.2) -> bool:
    """Missing-context guard: is anything actually relevant (semantic or graph above threshold)? If not,
    the caller should flag insufficient context rather than reason blindly."""
    return any(
        max(c["signals"]["semantic"], c["signals"]["graph"]) >= threshold for c in candidates
    )

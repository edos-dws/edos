"""Retriever (CP-13) — assembles a project's relevant context for reasoning.

"The LLM never searches the project. The Retriever does." Deterministic hybrid retrieval:
anchor extraction → dense (pgvector cosine kNN) + lexical (term overlap) + graph traversal/expansion +
recency → per-candidate signals. `select_context` then ranks those signals with the **semantic-led**
weight set (`ranking.blend` with `RETRIEVAL_WEIGHTS` + a bounded feedback nudge — the SAME single blend the
graph-led decision path uses, just different weights; see `ranking.py` for why the two paths differ) and
reranks top-50→top-K. A **missing-context guard** (`coverage_ok`) flags thin coverage instead of reasoning
blind. Temporal validity feeds the confidence signal so stale/superseded items rank down.

Note: `select_context` deliberately does NOT force-inject a "hard-constraint floor" of every requirement —
that re-injected the very distractors the reranker had dropped (see its docstring). `retrieve` still marks
must-see items with full `focus` so ranking/compression is biased to keep them; that is a soft bias, not a
hard override.

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
from edos.engines import graph_builder, ranking
from edos.engines.embeddings import EmbeddingProvider, default_embedder
from edos.engines.query_expansion import get_query_expander
from edos.engines.reranker import get_reranker

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
    dense_query: str | None = None,
) -> list[dict]:
    """Return ContextEngine-shaped candidates (`{type, ref_id, content, signals}`) for a project+question.

    `dense_query` overrides the text used for the dense (vector) search only — e.g. a HyDE-expanded query —
    while lexical/anchor matching still use the original `question`."""
    embedder = embedder or default_embedder()
    items = list(session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id)))
    if not items:
        return []

    qvec = embedder.embed(dense_query or question)
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
                "feedback": float(it.feedback_score or 0.0),  # learned usefulness (#7)
            },
        })
    return candidates


def coverage_ok(candidates: list[dict], threshold: float = 0.2) -> bool:
    """Missing-context guard: is anything actually relevant (semantic or graph above threshold)? If not,
    the caller should flag insufficient context rather than reason blindly."""
    return any(
        max(c["signals"]["semantic"], c["signals"]["graph"]) >= threshold for c in candidates
    )


# Human-readable provenance label per item type — so the LLM can tell a hard requirement from a prior
# decision from a loose note, and weight/cite accordingly (instead of one flat unlabeled blob).
_CONTEXT_LABEL = {
    "requirement": "REQUIREMENT", "decision": "PRIOR DECISION", "assumption": "ASSUMPTION",
    "risk": "RISK", "document": "DOCUMENT", "external": "SOURCE", "project": "PROJECT",
}


def label_for(item_type: str) -> str:
    """Provenance label for a candidate's item type (shared by assembly + the deep-dive context builder)."""
    return _CONTEXT_LABEL.get(item_type, "CONTEXT")


def _rank_score(signals: dict) -> float:
    """SELECTION/eval-path score: the semantic-led blend (`RETRIEVAL_WEIGHTS`) + a bounded ±feedback nudge.
    Thin wrapper over the SAME `ranking.blend` the decision path uses — only the weight set and the feedback
    term differ. WHY this path is semantic-led while the decision path is graph-led (and whether that split
    should survive) is a declared choice deferred to the A3 eval — see `ranking.py`."""
    return ranking.blend(signals, ranking.RETRIEVAL_WEIGHTS, feedback_weight=ranking.FEEDBACK_WEIGHT)


def select_context(
    session: Session, *, project_id: str, query: str, top_k: int = 8,
) -> list[dict]:
    """The candidate SELECTION for a query: `expand (HyDE) → retrieve → rank → rerank (top-50 → top-K)`.
    Returns the chosen candidate dicts (with `ref_id`) — the exact set the assembled context is built from,
    so the eval harness measures the real thing the LLM sees.

    The reranker cross-reads the query against each candidate and IS the relevance authority — it drops items
    that merely share keywords. We trust its top-K; on a no-op/empty result we fall back to the rank_score
    order. (We deliberately do NOT force-inject every "hard constraint": the old floor marked every
    requirement must-see, which re-injected the very distractors the reranker had dropped.)"""
    dense_query = get_query_expander().expand(query)  # HyDE: embed a hypothetical answer → better recall
    cands = retrieve(session, project_id=project_id, question=query, dense_query=dense_query)
    if not cands:
        return []
    for c in cands:
        c["_score"] = _rank_score(c["signals"])
    cands.sort(key=lambda c: -c["_score"])
    pool = cands[:50]
    order = get_reranker().rerank(query, [c["content"] for c in pool], top_k)
    return [pool[i] for i in order] if order else pool[:top_k]


def assemble_context(
    session: Session, *, project_id: str, query: str, top_k: int = 8, budget_chars: int = 4000,
) -> list[str]:
    """Context Engine → LLM: the selected candidates, labeled with provenance and capped to a char budget."""
    out: list[str] = []
    used = 0
    for c in select_context(session, project_id=project_id, query=query, top_k=top_k):
        line = f"[{label_for(c['type'])}] {c['content'].strip()}"
        if out and used + len(line) > budget_chars:
            break
        out.append(line)
        used += len(line)
    return out

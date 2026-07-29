"""Decision Graph view + decision diff + cross-decision contradictions (UI-CP-7).

Read-only projections over the persisted decision store, first-class assumptions, and the decision graph
(``graph_edges``) that feed the Decision Graph tab. This is deterministic software — no LLM: nodes/edges come
straight from what is persisted; the diff heuristic derives *why changed* / *affected* from the two versions'
contract bodies + ``decision_detail`` envelope. Nothing here is fabricated.

Responsibilities (one engine, one job — CLAUDE.md):
  * ``build_graph`` — decision + assumption nodes and the edges between them (deps/conflicts/supersedes/…),
    plus assumption→decision links from ``source_decision_id``. Node ids are the stable logical decision id
    and per-project assumption ``A{n}`` id so the frontend can lay them out deterministically.
  * ``decision_diff`` — struck-through old→new between two versions of a decision, with a heuristic
    ``why_changed`` and ``affected`` list. One-version decisions return an empty diff gracefully.
  * ``contradictions`` — the ``conflicts_with`` pairs (already surfaced by the graph builder + watchdog),
    resolved to labels with a short explanation.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import GraphEdge, ProjectItem
from edos.engines import assumptions as assumptions_engine
from edos.engines import decision_store
from edos.models.entities import RelationType

_CONFLICT = RelationType.conflicts_with.value
_SUPERSEDES = RelationType.supersedes.value

# directed decision-graph relations worth drawing as arrows (conflicts_with is handled separately as an
# undirected red edge).
_DIRECTED: frozenset[str] = frozenset({
    RelationType.depends_on.value, RelationType.supersedes.value, RelationType.influences.value,
    RelationType.references.value, RelationType.derived_from.value, RelationType.mitigates.value,
    RelationType.invalidates.value, RelationType.validates.value, RelationType.related_to.value,
})

# assumption statuses that mean "don't trust this now" → dashed node in the UI
_SHAKY_ASSUMPTION: frozenset[str] = frozenset({"challenged", "invalidated"})


# ==================================================================================================
# graph
# ==================================================================================================
def _decision_validity(node_id: str, edges: list[GraphEdge]) -> str:
    """Derive a decision node's temporal validity from the edges that touch it (decisions carry no validity
    column — ProjectItems do). An active ``conflicts_with`` wins, then a ``supersedes`` pointing at it."""
    for e in edges:
        if e.relation_type == _CONFLICT and e.validity == "active" and node_id in (e.source_id, e.target_id):
            return "conflicted"
    for e in edges:
        if e.relation_type == _SUPERSEDES and e.target_id == node_id:
            return "superseded"
    return "active"


def build_graph(session: Session, project_id: str) -> dict:
    """Nodes (latest-version decisions + first-class assumptions) + edges (graph relations between them,
    plus assumption→decision links)."""
    decisions = decision_store.list_for_project(session, project_id)
    assumption_rows = assumptions_engine.list_for_project(session, project_id)

    decision_ids = {d.id for d in decisions}
    node_ids = decision_ids | {a.id for a in assumption_rows}
    all_edges = list(session.scalars(select(GraphEdge)))

    nodes: list[dict] = []
    for d in decisions:
        nodes.append({
            "id": d.id, "type": "decision", "label": d.title,
            "status": d.status, "validity": _decision_validity(d.id, all_edges),
        })
    for a in assumption_rows:
        nodes.append({
            "id": a.id, "type": "assumption", "label": a.statement, "status": a.status,
            # dashed styling in the UI for a challenged/invalidated assumption
            "validity": "invalid" if a.status in _SHAKY_ASSUMPTION else "active",
        })

    edges: list[dict] = []
    seen_conflict: set[tuple[str, str]] = set()
    for e in all_edges:
        if e.source_id not in node_ids or e.target_id not in node_ids:
            continue  # only edges wholly inside this project's decision/assumption node set
        if e.relation_type == _CONFLICT:
            key = tuple(sorted((e.source_id, e.target_id)))
            if key in seen_conflict:
                continue  # dedupe the symmetric back-edge
            seen_conflict.add(key)
            edges.append({"source": key[0], "target": key[1], "relation": _CONFLICT, "conflict": True})
        elif e.relation_type in _DIRECTED:
            edges.append({"source": e.source_id, "target": e.target_id,
                          "relation": e.relation_type, "conflict": False})

    # assumption → decision links (first-class assumptions carry their source decision)
    for a in assumption_rows:
        if a.source_decision_id and a.source_decision_id in decision_ids:
            edges.append({"source": a.id, "target": a.source_decision_id,
                          "relation": "assumption_of", "conflict": False})

    return {"nodes": nodes, "edges": edges}


# ==================================================================================================
# contradictions (cross-decision)
# ==================================================================================================
def contradictions(session: Session, project_id: str) -> list[dict]:
    """The project's ``conflicts_with`` pairs, resolved to labels with a short explanation. Endpoints are
    resolved against decisions, first-class assumptions, and project items (a conflict can involve any)."""
    label: dict[str, tuple[str, str]] = {}
    for d in decision_store.list_for_project(session, project_id):
        label[d.id] = ("decision", d.title)
    for a in assumptions_engine.list_for_project(session, project_id):
        label.setdefault(a.id, ("assumption", a.statement))
    for it in session.scalars(select(ProjectItem).where(ProjectItem.project_id == project_id)):
        label.setdefault(it.id, ("item", (it.content or "")[:80]))

    pairs: list[dict] = []
    seen: set[tuple[str, str]] = set()
    # CONFIRMED contradictions only — exclude semantic proposals still `suspected` and human-`dismissed`
    # ones (those surface via the watchdog / suspected-conflicts endpoint, not here).
    for e in session.scalars(select(GraphEdge).where(
        GraphEdge.relation_type == _CONFLICT,
        GraphEdge.validity.not_in(["suspected", "dismissed"]),
    )):
        if e.source_id not in label or e.target_id not in label:
            continue
        key = tuple(sorted((e.source_id, e.target_id)))
        if key in seen:
            continue
        seen.add(key)
        a_id, b_id = key
        a_lbl, b_lbl = label[a_id][1], label[b_id][1]
        pairs.append({
            "a": a_id, "b": b_id, "a_type": label[a_id][0], "b_type": label[b_id][0],
            "a_label": a_lbl, "b_label": b_lbl, "validity": e.validity,
            "explanation": (f"“{a_lbl}” conflicts with “{b_lbl}” — both cannot hold at "
                            "once; resolve the conflict before relying on either."),
        })
    return pairs


# ==================================================================================================
# decision diff (between versions)
# ==================================================================================================
def _detail(row) -> dict:
    if not row or not row.decision_detail:
        return {}
    try:
        data = json.loads(row.decision_detail)
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _why_changed(from_row, to_row) -> list[str]:
    fd, td = decision_store.to_decision(from_row), decision_store.to_decision(to_row)
    reasons: list[str] = []
    if fd.summary != td.summary:
        reasons.append(f'Summary changed: "{fd.summary}" → "{td.summary}"')
    if fd.recommendation != td.recommendation:
        reasons.append("Recommendation was revised.")
    if from_row.status != to_row.status:
        reasons.append(f"Status advanced {from_row.status} → {to_row.status}.")
    if round(fd.confidence * 100) != round(td.confidence * 100):
        reasons.append(f"Coverage moved {round(fd.confidence * 100)}% → "
                       f"{round(td.confidence * 100)}%.")
    fa = {a.statement for a in fd.assumptions}
    ta = {a.statement for a in td.assumptions}
    for s in ta - fa:
        reasons.append(f"New assumption introduced: {s}")
    for s in fa - ta:
        reasons.append(f"Assumption dropped: {s}")
    # decision_impact deltas (persistence-envelope detail)
    f_impact = {(i.get("area"), i.get("change")) for i in (_detail(from_row).get("decision_impact") or [])}
    for area, change in [(i.get("area"), i.get("change"))
                         for i in (_detail(to_row).get("decision_impact") or [])]:
        if (area, change) not in f_impact:
            reasons.append(f"Impact on {area}: {change}")
    return reasons


def _affected(from_row, to_row) -> list[str]:
    """Union of impacted components + decision-impact areas + affected decisions across both versions."""
    affected: list[str] = []

    def add(x) -> None:
        if x and x not in affected:
            affected.append(x)

    for row in (from_row, to_row):
        if row is None:
            continue
        det = _detail(row)
        for c in det.get("impacted_components") or []:
            add(c)
        for i in det.get("decision_impact") or []:
            add(i.get("area"))
        for ad in decision_store.to_decision(row).affected_decisions:
            add(ad)
    return affected


def decision_diff(
    session: Session, decision_id: str, from_v: int | None = None, to_v: int | None = None
) -> dict | None:
    """Diff two versions of a decision. Defaults: ``to`` = latest, ``from`` = latest's ``parent_version``.
    A single-version decision (no parent) returns an empty diff gracefully. Returns None if the decision does
    not exist (endpoint maps to 404)."""
    latest = decision_store.get_latest(session, decision_id)
    if latest is None:
        return None

    to_version = to_v if to_v is not None else latest.version
    to_row = decision_store.get_version(session, decision_id, to_version) or latest
    from_version = from_v if from_v is not None else latest.parent_version

    empty = {
        "decision_id": decision_id, "from_version": None, "to_version": to_row.version,
        "from_summary": None, "to_summary": to_row.title,
        "why_changed": [], "affected": _affected(None, to_row),
    }
    if from_version is None:
        return empty
    from_row = decision_store.get_version(session, decision_id, from_version)
    if from_row is None:
        return empty
    return {
        "decision_id": decision_id,
        "from_version": from_row.version, "to_version": to_row.version,
        "from_summary": from_row.title, "to_summary": to_row.title,
        "why_changed": _why_changed(from_row, to_row),
        "affected": _affected(from_row, to_row),
    }

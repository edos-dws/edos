"""A5 — semantic graph edges: kNN candidates → LLM classify → low-stakes apply, high-stakes surface."""
from sqlalchemy import select

from edos.db.models import GraphEdge, ProjectItem
from edos.engines import graph_semantic, graph_view, ingestion, watchdog


class _EdgeRouter:
    """Fake ModelRouter whose relationship call returns fixed proposed edges."""
    def __init__(self, edges):
        self.edges = edges
    def execute(self, capability, context, schema=None, tier=None):
        return {"edges": self.edges}


class _RaisingRouter:
    def execute(self, capability, context, schema=None, tier=None):
        from edos.engines.prompt import MalformedOutputError
        raise MalformedOutputError("no valid edges")


def _seed(session):
    # two lexically-overlapping items so the stub retriever surfaces B as a candidate for A
    ingestion.ingest_item(session, id="A", project_id="pg", item_type="decision",
                          content="pH sensor calibration drift over temperature range")
    ingestion.ingest_item(session, id="B", project_id="pg", item_type="decision",
                          content="pH sensor temperature compensation coefficient")
    session.flush()


def _edge(session, src, tgt):
    return session.scalars(select(GraphEdge).where(
        GraphEdge.source_id == src, GraphEdge.target_id == tgt)).first()


def test_low_stakes_edge_is_applied_with_semantic_origin(session):
    _seed(session)
    router = _EdgeRouter([{"target_id": "B", "relation": "related_to", "confidence": 0.9,
                           "rationale": "both about pH sensor thermal behaviour"}])
    out = graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)
    assert any(e["target_id"] == "B" for e in out["applied"])
    edge = _edge(session, "A", "B")
    assert edge is not None
    assert edge.origin == "semantic"                       # distinguishable from author-declared
    assert edge.rationale                                   # auditable — why the edge exists


def test_high_stakes_conflict_is_surfaced_not_auto_applied(session):
    _seed(session)
    router = _EdgeRouter([{"target_id": "B", "relation": "conflicts_with", "confidence": 0.95,
                           "rationale": "incompatible calibration assumptions"}])
    out = graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)
    assert any(e["target_id"] == "B" for e in out["suspected"])   # surfaced for confirmation
    assert out["applied"] == []                                    # NOT auto-applied
    # B2: it IS persisted, but as a SUSPECTED edge (not an active conflict)
    edge = _edge(session, "A", "B")
    assert edge is not None and edge.validity == "suspected" and edge.origin == "semantic"
    # crucially: neither node's validity was flipped to "conflicted"
    assert session.get(ProjectItem, "A").validity == "active"
    assert session.get(ProjectItem, "B").validity == "active"
    # and it does NOT leak into the CONFIRMED contradictions view
    assert graph_view.contradictions(session, "pg") == []


def test_suspected_conflict_is_listed_and_surfaced_by_watchdog(session):
    _seed(session)
    router = _EdgeRouter([{"target_id": "B", "relation": "conflicts_with", "confidence": 0.9,
                           "rationale": "opposite calibration assumptions"}])
    graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)
    listed = graph_semantic.list_suspected(session, "pg")
    assert len(listed) == 1 and listed[0]["source_id"] == "A" and listed[0]["target_id"] == "B"
    assert listed[0]["rationale"]
    alerts = watchdog.scan(session, "pg")
    assert any(a.type == "suspected_conflict" and "B" in a.message for a in alerts)


def test_confirm_suspected_applies_conflict_and_flips_validity(session):
    _seed(session)
    router = _EdgeRouter([{"target_id": "B", "relation": "conflicts_with", "confidence": 0.9,
                           "rationale": "x"}])
    graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)
    res = graph_semantic.confirm_suspected(session, "A", "B", "conflicts_with")
    assert res["confirmed"] is True
    # now a real conflict: both nodes conflicted, symmetric edges active, no suspected left
    assert session.get(ProjectItem, "A").validity == "conflicted"
    assert session.get(ProjectItem, "B").validity == "conflicted"
    assert _edge(session, "A", "B").validity == "active"
    assert _edge(session, "B", "A").validity == "active"          # symmetric back-edge
    assert graph_semantic.list_suspected(session, "pg") == []
    assert len(graph_view.contradictions(session, "pg")) == 1     # now in the confirmed view


def test_dismiss_suspected_marks_dismissed_and_leaves_nodes_active(session):
    _seed(session)
    router = _EdgeRouter([{"target_id": "B", "relation": "conflicts_with", "confidence": 0.9, "rationale": "x"}])
    graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)
    res = graph_semantic.dismiss_suspected(session, "A", "B", "conflicts_with")
    assert res["dismissed"] == 1
    assert _edge(session, "A", "B").validity == "dismissed"
    assert graph_semantic.list_suspected(session, "pg") == []     # no longer pending
    assert session.get(ProjectItem, "A").validity == "active"     # never touched trust
    assert not any(a.type == "suspected_conflict" for a in watchdog.scan(session, "pg"))


def test_confirm_unknown_pair_returns_reason_not_crash(session):
    _seed(session)
    res = graph_semantic.confirm_suspected(session, "A", "B", "conflicts_with")
    assert res["confirmed"] is False and "no suspected" in res["reason"]


def test_suspected_not_recreated_when_already_present(session):
    _seed(session)
    router = _EdgeRouter([{"target_id": "B", "relation": "conflicts_with", "confidence": 0.9, "rationale": "x"}])
    graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)
    graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)  # re-run (idempotent)
    assert len(graph_semantic.list_suspected(session, "pg")) == 1


def test_below_confidence_edge_is_skipped(session):
    _seed(session)
    router = _EdgeRouter([{"target_id": "B", "relation": "related_to", "confidence": 0.2, "rationale": "weak"}])
    out = graph_semantic.propose_semantic_edges(session, "pg", "A", router=router, min_confidence=0.6)
    assert out["applied"] == [] and _edge(session, "A", "B") is None


def test_edge_to_non_candidate_target_is_ignored(session):
    _seed(session)
    # the classifier hallucinates a target that was never a candidate → ignored (no dangling edge)
    router = _EdgeRouter([{"target_id": "GHOST", "relation": "related_to", "confidence": 0.9, "rationale": "x"}])
    out = graph_semantic.propose_semantic_edges(session, "pg", "A", router=router)
    assert out["applied"] == []


def test_offline_malformed_router_degrades_to_no_edges(session):
    _seed(session)
    out = graph_semantic.propose_semantic_edges(session, "pg", "A", router=_RaisingRouter())
    assert out == {"applied": [], "suspected": []}
    assert _edge(session, "A", "B") is None

"""A5 — semantic graph edges: kNN candidates → LLM classify → low-stakes apply, high-stakes surface."""
from sqlalchemy import select

from edos.db.models import GraphEdge, ProjectItem
from edos.engines import graph_semantic, ingestion


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
    assert _edge(session, "A", "B") is None                        # no edge written
    # and crucially: neither node's validity was flipped to "conflicted"
    assert session.get(ProjectItem, "A").validity == "active"
    assert session.get(ProjectItem, "B").validity == "active"


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

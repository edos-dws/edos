"""Ticket 2.2 — Decision Graph edges: traversal + Ch 15 weights."""
from edos.db.graph import DEFAULT_WEIGHT, neighbors, weight_for
from edos.db.models import GraphEdge
from edos.models.entities import RelationType


def test_ch15_weights():
    assert weight_for(RelationType.depends_on) == 10.0
    assert weight_for(RelationType.influences) == 8.0
    assert weight_for(RelationType.invalidates) == 7.0
    assert weight_for(RelationType.mitigates) == 6.0
    assert weight_for(RelationType.related_to) == 3.0
    # a type without a Ch15 weight falls back to the documented default
    assert weight_for(RelationType.created_by) == DEFAULT_WEIGHT


def test_traverse_depends_on(session):
    session.add_all([
        GraphEdge(source_id="D-1", target_id="R-3", relation_type="depends_on", confidence=0.9),
        GraphEdge(source_id="D-1", target_id="A-2", relation_type="influences", confidence=0.7),
        GraphEdge(source_id="D-9", target_id="R-3", relation_type="depends_on", confidence=0.5),
    ])
    session.commit()

    all_out = neighbors(session, "D-1")
    assert {e.target_id for e in all_out} == {"R-3", "A-2"}

    dep_only = neighbors(session, "D-1", RelationType.depends_on)
    assert [e.target_id for e in dep_only] == ["R-3"]

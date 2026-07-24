"""CP-12 — graph builder: edge extraction, integrity (dangling/DAG/symmetric), temporal validity."""
import pytest

from edos.db.models import GraphEdge, ProjectItem
from edos.engines import graph_builder as gb
from edos.models.entities import RelationType


def _item(session, iid, content="x"):
    session.add(ProjectItem(id=iid, project_id="p1", item_type="requirement", content=content))
    session.flush()


def test_extract_edges_infers_relation_from_keyword():
    edges = gb.extract_edges("This supersedes DEC-1 and depends on REQ-2", ["DEC-1", "REQ-2", "REQ-9"])
    rel = dict(edges)
    assert rel["DEC-1"] is RelationType.supersedes
    assert rel["REQ-2"] is RelationType.depends_on
    assert "REQ-9" not in rel  # not mentioned


def test_dangling_edge_rejected(session):
    _item(session, "A")
    with pytest.raises(gb.GraphIntegrityError):
        gb.add_edge(session, source_id="A", target_id="ghost", relation=RelationType.references)


def test_supersedes_cycle_rejected(session):
    _item(session, "A")
    _item(session, "B")
    gb.add_edge(session, source_id="A", target_id="B", relation=RelationType.supersedes)
    with pytest.raises(gb.GraphIntegrityError):
        gb.add_edge(session, source_id="B", target_id="A", relation=RelationType.supersedes)


def test_supersedes_marks_target_superseded(session):
    _item(session, "A")
    _item(session, "B")
    gb.add_edge(session, source_id="A", target_id="B", relation=RelationType.supersedes)
    assert session.get(ProjectItem, "B").validity == "superseded"


def test_conflicts_with_is_symmetric_and_marks_both(session):
    _item(session, "A")
    _item(session, "B")
    gb.add_edge(session, source_id="A", target_id="B", relation=RelationType.conflicts_with)
    assert session.get(ProjectItem, "A").validity == "conflicted"
    assert session.get(ProjectItem, "B").validity == "conflicted"
    # both directions exist
    dirs = {(e.source_id, e.target_id) for e in session.query(GraphEdge)
            .filter(GraphEdge.relation_type == "conflicts_with")}
    assert ("A", "B") in dirs and ("B", "A") in dirs

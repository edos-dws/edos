"""UI-CP-7 — Decision Graph + cross-decision contradictions + decision diff.

Engine-level tests (graph_view) over a real session plus REST-surface tests via TestClient. DB tests SKIP
when Postgres is unreachable (see conftest), so the gate stays green without infra.
"""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import assumptions as assumptions_engine
from edos.engines import decision_store, graph_view
from edos.engines.graph_builder import add_edge
from edos.models.decision import Decision
from edos.models.entities import RelationType


def _decision(summary, rec, *, conf=0.7, assumptions=None):
    return Decision(
        summary=summary, recommendation=rec, confidence=conf, status="recommended",
        assumptions=assumptions or [],
        evidence=[{"claim": "grounded", "source": "REQ-1", "kind": "fact"}],
    )


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------ engine: graph
def test_build_graph_nodes_edges_and_conflict(session):
    pid = "proj-g"
    d1 = decision_store.save_new(
        session, id="DEC-1", project_id=pid,
        decision=_decision("Passive balancing", "Use passive balancing",
                           assumptions=[{"statement": "Cell spread stays under 40mV", "confidence": 0.6,
                                         "risk_if_wrong": "Active balancing needed"}]),
    )
    decision_store.save_new(
        session, id="DEC-2", project_id=pid,
        decision=_decision("Sealed IP67 enclosure", "Seal the pack"),
    )
    assumptions_engine.upsert_from_decision(session, pid, decision_store.to_decision(d1), d1.id)
    # cross-decision conflict between the two decisions (symmetric edge)
    add_edge(session, source_id="DEC-1", target_id="DEC-2", relation=RelationType.conflicts_with)
    session.commit()

    g = graph_view.build_graph(session, pid)
    types = sorted({n["type"] for n in g["nodes"]})
    assert types == ["assumption", "decision"]
    dec_nodes = [n for n in g["nodes"] if n["type"] == "decision"]
    assert {n["id"] for n in dec_nodes} == {"DEC-1", "DEC-2"}
    # a conflicts_with edge marks the touched decisions as conflicted
    assert all(n["validity"] == "conflicted" for n in dec_nodes)

    # exactly one (deduped, undirected) conflict edge, flagged
    conflict_edges = [e for e in g["edges"] if e.get("conflict")]
    assert len(conflict_edges) == 1
    assert conflict_edges[0]["relation"] == "conflicts_with"

    # assumption node + assumption→decision link
    asm = [n for n in g["nodes"] if n["type"] == "assumption"]
    assert len(asm) == 1
    links = [e for e in g["edges"] if e["relation"] == "assumption_of"]
    assert links and links[0]["target"] == "DEC-1"


def test_assumption_status_drives_dashed(session):
    pid = "proj-dash"
    d = decision_store.save_new(session, id="DEC-x", project_id=pid,
                                decision=_decision("D", "do it"))
    a = assumptions_engine.create(session, pid, "Ambient stays below 40C", source_decision_id=d.id)
    assumptions_engine.set_status(session, aid=a.id, status="challenged", project_id=pid)
    session.commit()
    node = next(n for n in graph_view.build_graph(session, pid)["nodes"] if n["type"] == "assumption")
    assert node["status"] == "challenged"
    assert node["validity"] == "invalid"  # → dashed in the UI


# ------------------------------------------------------------------ engine: contradictions
def test_contradictions_pairs(session):
    pid = "proj-c"
    decision_store.save_new(session, id="DEC-A", project_id=pid, decision=_decision("Forced-air cooling", "fan"))
    decision_store.save_new(session, id="DEC-B", project_id=pid, decision=_decision("IP67 sealed", "seal"))
    add_edge(session, source_id="DEC-A", target_id="DEC-B", relation=RelationType.conflicts_with)
    session.commit()

    pairs = graph_view.contradictions(session, pid)
    assert len(pairs) == 1
    p = pairs[0]
    assert {p["a"], p["b"]} == {"DEC-A", "DEC-B"}
    assert "conflicts with" in p["explanation"]
    assert p["a_type"] == "decision" and p["b_type"] == "decision"


# ------------------------------------------------------------------ engine: diff
def test_diff_two_versions(session):
    pid = "proj-d"
    d = decision_store.save_new(
        session, id="DEC-D", project_id=pid,
        decision=_decision("Balancing = passive", "Use passive balancing", conf=0.6),
    )
    # accept with an edited decision → v2 (changed summary + affected decision)
    edited = _decision("Balancing = active", "Switch to active balancing", conf=0.8)
    edited = edited.model_copy(update={"affected_decisions": ["DEC-OTHER"]})
    decision_store.accept(session, d.id, edited=edited)
    session.commit()

    diff = graph_view.decision_diff(session, "DEC-D")
    assert diff["from_version"] == 1 and diff["to_version"] == 2
    assert diff["from_summary"] == "Balancing = passive"
    assert diff["to_summary"] == "Balancing = active"
    assert any("Summary changed" in w for w in diff["why_changed"])
    assert any("Status advanced" in w for w in diff["why_changed"])
    assert "DEC-OTHER" in diff["affected"]


def test_diff_single_version_is_empty(session):
    pid = "proj-s"
    decision_store.save_new(session, id="DEC-S", project_id=pid, decision=_decision("Only version", "do"))
    session.commit()
    diff = graph_view.decision_diff(session, "DEC-S")
    assert diff["from_version"] is None
    assert diff["from_summary"] is None
    assert diff["to_summary"] == "Only version"
    assert diff["why_changed"] == []


def test_diff_explicit_from_to(session):
    pid = "proj-e"
    d = decision_store.save_new(session, id="DEC-E", project_id=pid, decision=_decision("v1 summary", "r1"))
    decision_store.accept(session, d.id)  # v2
    decision_store.accept(session, d.id)  # v3
    session.commit()
    diff = graph_view.decision_diff(session, "DEC-E", from_v=1, to_v=3)
    assert diff["from_version"] == 1 and diff["to_version"] == 3
    assert any("Status advanced" in w for w in diff["why_changed"])


# ------------------------------------------------------------------ REST surface
def test_graph_endpoints(client):
    pid = client.post("/v1/projects", json={"name": "Graph P"}).json()["id"]
    dec = {
        "schema_version": "edos.decision.v1", "summary": "Host MCU = ESP32", "recommendation": "use it",
        "confidence": 0.8, "status": "recommended",
        "assumptions": [{"statement": "BLE range is sufficient", "confidence": 0.5}],
        "evidence": [{"claim": "cheap", "source": "REQ-1", "kind": "fact"}],
    }
    r1 = client.post("/v1/decisions", json={"project_id": pid, "decision": dec})
    id1 = r1.json()["id"]
    dec2 = {**dec, "summary": "Wired UART link", "assumptions": []}
    id2 = client.post("/v1/decisions", json={"project_id": pid, "decision": dec2}).json()["id"]

    g = client.get(f"/v1/projects/{pid}/graph").json()
    assert len([n for n in g["nodes"] if n["type"] == "decision"]) == 2
    assert any(n["type"] == "assumption" for n in g["nodes"])

    # diff default on a single-version decision → graceful empty
    diff = client.get(f"/v1/decisions/{id1}/diff").json()
    assert diff["from_version"] is None
    # accept twice → 2 versions, then diff has a status delta
    client.post(f"/v1/decisions/{id2}/accept", json={})
    diff2 = client.get(f"/v1/decisions/{id2}/diff").json()
    assert diff2["from_version"] == 1 and diff2["to_version"] == 2

    # unknown project / decision → 404
    assert client.get("/v1/projects/nope/graph").status_code == 404
    assert client.get("/v1/projects/nope/contradictions").status_code == 404
    assert client.get("/v1/decisions/nope/diff").status_code == 404

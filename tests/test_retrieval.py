"""CP-13 — Retriever: hybrid signals, graph expansion, hard-constraint floor, missing-context guard."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import ingestion, retrieval


def _ingest(session, iid, itype, content):
    return ingestion.ingest_item(session, id=iid, project_id="p1", item_type=itype, content=content)


def _by_ref(cands):
    return {c["ref_id"]: c for c in cands}


def test_relevant_item_scores_higher_than_unrelated(session):
    _ingest(session, "REQ-1", "requirement", "measure pH TDS temperature dissolved oxygen with sensors")
    _ingest(session, "REQ-2", "requirement", "quarterly financial revenue accounting report")
    cands = _by_ref(retrieval.retrieve(session, project_id="p1", question="pH dissolved oxygen sensor"))
    assert cands["REQ-1"]["signals"]["semantic"] > cands["REQ-2"]["signals"]["semantic"]


def test_graph_expansion_surfaces_linked_decision(session):
    _ingest(session, "REQ-1", "requirement", "read pH sensor")
    _ingest(session, "DEC-1", "decision", "host MCU decision depends on REQ-1 for sensor interface")
    # question anchors on REQ-1 (token overlap) → graph expansion should reach DEC-1
    cands = _by_ref(retrieval.retrieve(session, project_id="p1", question="pH sensor requirement"))
    assert cands["DEC-1"]["signals"]["graph"] > 0.0


def test_active_requirement_is_floored_with_full_focus(session):
    _ingest(session, "REQ-9", "requirement", "unrelated compliance clause about packaging")
    cands = _by_ref(retrieval.retrieve(session, project_id="p1", question="battery runtime"))
    assert cands["REQ-9"]["signals"]["focus"] == 1.0  # hard-constraint floor


def test_superseded_item_ranks_down_via_confidence(session):
    _ingest(session, "DEC-1", "decision", "use ESP32 as host")
    _ingest(session, "DEC-2", "decision", "this supersedes DEC-1, use nRF52 as host")  # marks DEC-1 superseded
    cands = _by_ref(retrieval.retrieve(session, project_id="p1", question="host MCU"))
    assert cands["DEC-1"]["signals"]["confidence"] < cands["DEC-2"]["signals"]["confidence"]


def test_coverage_guard_unit():
    thin = [{"signals": {"semantic": 0.1, "graph": 0.0}}]
    ok = [{"signals": {"semantic": 0.6, "graph": 0.0}}]
    assert retrieval.coverage_ok(thin) is False
    assert retrieval.coverage_ok(ok) is True


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_analyze_uses_retrieved_context_end_to_end(client):
    pid = client.post("/v1/projects", json={"name": "WQ"}).json()["id"]
    client.post(f"/v1/projects/{pid}/items",
                json={"id": "REQ-1", "item_type": "requirement",
                      "content": "measure pH TDS temperature dissolved oxygen; pick a host MCU"})
    # no context_items — the retriever must assemble context from the project
    resp = client.post("/v1/analyze", json={"project_id": pid, "question": "which MCU for pH sensor"})
    assert resp.status_code == 200
    assert resp.json().get("status") in {"recommended", "needs_clarification"}

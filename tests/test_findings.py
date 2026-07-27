"""UI-CP-3 — Engineering Review → Findings (rules + graph + LLM/heuristic merge)."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import findings

CATEGORIES = set(findings.CATEGORIES)
FINDING_KEYS = {"category", "severity", "title", "detail", "if_ignored", "evidence"}

# A representative BMS review input (matches the walkthrough Stage-1 scenario).
BMS_TEXT = ("I want to design a 14S 100A BMS for an LFP battery pack in an EV. It supports charging, "
            "discharging and communicates over CAN. Priority is safety, reliability and cost optimization "
            "for mass production, using an STM32F4.")


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _new_project(client) -> str:
    return client.post("/v1/projects", json={"name": "BMS"}).json()["id"]


def _decision(summary: str, recommendation: str) -> dict:
    return {
        "summary": summary, "recommendation": recommendation, "confidence": 0.6,
        "status": "recommended",
        "evidence": [{"claim": "test context", "source": "test", "kind": "inference"}],
    }


# ---- schema / shape ----
def test_finding_dataclass_shape():
    f = findings.Finding(category="assumption", severity="high", title="t", detail="d",
                         if_ignored=["x"], evidence=["e"])
    assert set(f.to_dict()) == FINDING_KEYS
    assert f.category in CATEGORIES


def test_severity_info_maps_to_low():
    assert findings._norm_severity("info") == "low"
    assert findings._norm_severity("bogus") == "medium"


# ---- domain rules → hidden_dependency / best_practice ----
def test_rule_findings_emit_hidden_dependency_with_consequences():
    # "battery" + "18650" trips the power-budget best_practice rule; "ble" trips radio-mcu hidden_dependency.
    fs = findings._rule_findings("A BLE sensor on an 18650 battery, always-on.")
    cats = {f.category for f in fs}
    assert "hidden_dependency" in cats            # radio-mcu
    assert "best_practice" in cats                # power-budget
    for f in fs:
        assert f.if_ignored and f.evidence        # every rule finding carries consequences + evidence
        assert f.severity in {"critical", "high", "medium", "low"}   # "info" normalized away


# ---- LLM (heuristic offline) → assumption / optimization ----
def test_heuristic_probes_infer_assumptions_and_optimizations():
    fs = findings._heuristic_findings(BMS_TEXT)
    titles = {f.title for f in fs}
    cats = {f.category for f in fs}
    assert "assumption" in cats and "optimization" in cats
    assert "Cell balancing strategy not specified" in titles       # inferred, no explicit "assume"
    assert "Temperature sensing strategy missing" in titles
    for f in fs:
        assert f.if_ignored                                        # consequences present


def test_heuristic_captures_explicit_assumption():
    fs = findings._heuristic_findings("Design an MCU board; I assume the CAN bus runs at 500kbps.")
    assert any(f.category == "assumption" for f in fs)


# ---- contradictions ----
def test_stance_contradiction_vs_stored_decision(client):
    pid = _new_project(client)
    client.post("/v1/decisions", json={
        "project_id": pid,
        "decision": _decision("Use passive cell balancing", "Passive balancing keeps BOM cost down"),
        "status": "accepted"})
    r = client.post(f"/v1/projects/{pid}/review",
                    json={"text": "We'll switch to active balancing for better accuracy."})
    fs = r.json()["findings"]
    contradictions = [f for f in fs if f["category"] == "contradiction"]
    assert contradictions
    assert contradictions[0]["severity"] == "critical"
    assert "balancing" in contradictions[0]["detail"].lower()


def test_stance_contradiction_on_compute_tier(client):
    """Feature 4 — broader contradiction concepts: committing to bare-metal MCU after a stored Linux/MPU
    decision (or vice-versa) must surface as a critical contradiction, not slip through."""
    pid = _new_project(client)
    client.post("/v1/decisions", json={
        "project_id": pid,
        "decision": _decision("Compute platform",
                              "We will use an application processor running embedded linux for the camera stack"),
        "status": "accepted"})
    r = client.post(f"/v1/projects/{pid}/review",
                    json={"text": "Let's use a bare-metal MCU (cortex-m) to cut power and cost."})
    contradictions = [f for f in r.json()["findings"] if f["category"] == "contradiction"]
    assert contradictions
    assert "compute tier" in contradictions[0]["detail"].lower()


def test_graph_conflict_becomes_contradiction(client, session):
    pid = _new_project(client)
    a = client.post(f"/v1/projects/{pid}/items",
                    json={"item_type": "requirement", "content": "Enclosure is IP67 sealed"}).json()["id"]
    b = client.post(f"/v1/projects/{pid}/items",
                    json={"item_type": "requirement", "content": "Cooling uses forced-air ventilation"}).json()["id"]
    # explicit conflict edge (reuses graph_builder integrity + temporal side-effects)
    from edos.engines import graph_builder
    graph_builder.add_edge(session, source_id=a, target_id=b, relation="conflicts_with")
    session.flush()
    fs = findings.review(session, pid, "unrelated review text")
    conflicts = [f for f in fs if f.category == "contradiction"]
    assert conflicts and conflicts[0].category == "contradiction"


# ---- merge / sort / endpoint ----
def test_review_sorted_critical_first_and_deduped(client):
    pid = _new_project(client)
    client.post("/v1/decisions", json={
        "project_id": pid,
        "decision": _decision("Use passive cell balancing", "cost"),
        "status": "accepted"})
    fs = client.post(f"/v1/projects/{pid}/review", json={"text": BMS_TEXT + " Use active balancing."}).json()["findings"]
    order = [{"critical": 0, "high": 1, "medium": 2, "low": 3}[f["severity"]] for f in fs]
    assert order == sorted(order)                                  # severity-sorted, critical first
    keys = [(f["category"], f["title"]) for f in fs]
    assert len(keys) == len(set(keys))                            # de-duped


def test_review_endpoint_shape_and_categories(client):
    pid = _new_project(client)
    body = client.post(f"/v1/projects/{pid}/review", json={"text": BMS_TEXT}).json()
    assert body["count"] == len(body["findings"]) and body["findings"]
    for f in body["findings"]:
        assert set(f) == FINDING_KEYS
        assert f["category"] in CATEGORIES
        assert f["severity"] in {"critical", "high", "medium", "low"}
    cats = {f["category"] for f in body["findings"]}
    assert {"assumption"} & cats                                  # at least the inferred assumptions surface


def test_review_save_ingests_context(client):
    pid = _new_project(client)
    before = len(client.get(f"/v1/projects/{pid}/items").json())
    r = client.post(f"/v1/projects/{pid}/review", json={"text": BMS_TEXT, "save": True}).json()
    assert r["saved"]
    after = len(client.get(f"/v1/projects/{pid}/items").json())
    assert after == before + len(r["saved"])


def test_review_missing_project_404(client):
    assert client.post("/v1/projects/nope/review", json={"text": "x"}).status_code == 404

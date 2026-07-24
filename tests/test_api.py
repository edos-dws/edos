"""Ticket 7.1 + CP-13 — FastAPI endpoints wired to the engines (analyze now DB-backed via the retriever)."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.models.decision import Decision, validate_against_contract


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _cand(type_, ref, content, g=0.9, s=0.9, r=0.9, c=0.9, f=0.9):
    return {"type": type_, "ref_id": ref, "content": content,
            "signals": {"graph": g, "semantic": s, "recency": r, "confidence": c, "focus": f}}


def test_analyze_returns_contract_valid_decision(client):
    resp = client.post("/v1/analyze", json={
        "project_id": "p1",
        "question": "Is the nRF52840 right for LoRaWAN?",
        "context_items": [_cand("requirement", "R-3", "LoRaWAN reporting")],
    })
    assert resp.status_code == 200
    body = resp.json()
    validate_against_contract(body)          # decision-schema-valid
    assert body["status"] == "recommended"   # never frozen


def test_analyze_without_context_asks_for_clarification(client):
    resp = client.post("/v1/analyze", json={"project_id": "p1", "question": "?", "context_items": []})
    assert resp.status_code == 200
    assert resp.json()["status"] == "needs_clarification"


def test_verify_endpoint_runs_the_safety_pass(client):
    decision = Decision(
        summary="s", recommendation="r", confidence=0.8, status="recommended", evidence=[],
    ).to_contract_dict()
    resp = client.post("/v1/verify", json={"decision": decision})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"]["agreement"] is False           # no evidence => disagree
    assert body["decision"]["freeze_blockers"]             # blockers recorded


def test_ask_endpoint_returns_intent(client):
    resp = client.post("/v1/ask", json={"project_id": "p1", "question": "hello"})
    assert resp.status_code == 200
    assert resp.json()["intent"]["capability"] == "intent"

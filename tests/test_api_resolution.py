"""CP-15 — resolution + write-back + clarification-loop endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from edos.api.app import app
from edos.api.deps import get_session
from edos.db.models import ProjectItem

DECISION = {
    "schema_version": "edos.decision.v1", "summary": "Use ESP32-C6",
    "recommendation": "Adopt ESP32-C6 host MCU", "confidence": 0.8, "status": "recommended",
    "evidence": [{"claim": "BLE 5.3", "source": "datasheet", "kind": "fact"}],
    "freeze_blockers": ["Unconfirmed: assumption about ADC accuracy pending"],
}


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_accept_triggers_writeback(client, session):
    pid = client.post("/v1/projects", json={"name": "WQ"}).json()["id"]
    did = client.post("/v1/decisions", json={"project_id": pid, "decision": DECISION}).json()["id"]
    before = len(session.scalars(select(ProjectItem).where(ProjectItem.project_id == pid)).all())
    client.post(f"/v1/decisions/{did}/accept", json={})
    after = len(session.scalars(select(ProjectItem).where(ProjectItem.project_id == pid)).all())
    assert after > before  # knowledge folded back into the project


def test_resolve_assumption_endpoint(client):
    did = client.post("/v1/decisions", json={"project_id": "p1", "decision": DECISION}).json()["id"]
    r = client.post(f"/v1/decisions/{did}/assumptions/resolve",
                    json={"statement": "assumption about ADC accuracy",
                          "resolution": "validated on bench", "resolved_by": "eng-1"})
    assert r.status_code == 200
    assert r.json()["version"] == 2
    assert r.json()["decision"]["freeze_blockers"] == []


def test_clarification_answer_loop(client):
    r = client.post("/v1/analyze/answer", json={
        "project_id": "p1", "question": "Which MCU?",
        "answers": ["Battery is 18650", "BLE required", "BOM under $12"]})
    assert r.status_code == 200
    assert r.json().get("status") in {"recommended", "needs_clarification"}

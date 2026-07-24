"""CP-11 — decision persistence REST endpoints."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session

DECISION = {
    "schema_version": "edos.decision.v1",
    "summary": "Host MCU = ESP32-C6",
    "recommendation": "Use ESP32-C6 for sub-$12 BOM",
    "confidence": 0.82,
    "status": "recommended",
    "evidence": [{"claim": "cheap + BLE", "source": "REQ-5", "kind": "fact"}],
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


def test_persist_get_history_accept(client):
    # persist
    r = client.post("/v1/decisions", json={"project_id": "p1", "decision": DECISION})
    assert r.status_code == 201
    did = r.json()["id"]
    assert r.json()["version"] == 1
    assert r.json()["decision"]["summary"] == "Host MCU = ESP32-C6"

    # get latest
    assert client.get(f"/v1/decisions/{did}").json()["status"] == "recommended"

    # accept -> v2
    r = client.post(f"/v1/decisions/{did}/accept", json={})
    assert r.json()["version"] == 2
    assert r.json()["status"] == "accepted"

    # history has both, v1 immutable
    hist = client.get(f"/v1/decisions/{did}/history").json()
    assert [h["version"] for h in hist] == [1, 2]
    assert hist[0]["status"] == "recommended"


def test_list_project_decisions(client):
    pid = client.post("/v1/projects", json={"name": "P1"}).json()["id"]
    client.post("/v1/decisions", json={"project_id": pid, "decision": DECISION})
    listed = client.get(f"/v1/projects/{pid}/decisions").json()
    assert len(listed) == 1
    assert listed[0]["decision"]["summary"] == "Host MCU = ESP32-C6"
    # unknown project -> 404
    assert client.get("/v1/projects/nope/decisions").status_code == 404


def test_missing_decision_is_404(client):
    assert client.get("/v1/decisions/nope").status_code == 404
    assert client.get("/v1/decisions/nope/history").status_code == 404
    assert client.post("/v1/decisions/nope/accept", json={}).status_code == 404

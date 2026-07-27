"""Wave 3 · Step 6 — the reasoning-first FRAME endpoint (reflect back before deciding)."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_frame_endpoint_returns_direction_and_lenses(client):
    pid = client.post("/v1/projects", json={"name": "Battery sensor", "domain": "embedded"}).json()["id"]
    # seed a little project context so the spine has something to derive from
    client.post(f"/v1/projects/{pid}/items",
                json={"content": "Li-ion battery powered BLE sensor on a Cortex-M MCU, IP67 sealed.",
                      "item_type": "requirement"})
    r = client.post(f"/v1/projects/{pid}/deepdive/frame", json={"topic": "select the radio module"})
    assert r.status_code == 200
    body = r.json()
    assert body["topic"] == "select the radio module"
    assert "spine" in body and "lenses" in body and "framing_questions" in body
    assert isinstance(body["lenses"], list) and body["lenses"]           # weighted lenses present
    # each lens exposes what the UI needs to show + let the engineer override the emphasis
    first = body["lenses"][0]
    assert {"id", "title", "weight", "deep", "reason"} <= set(first)


def test_frame_on_missing_project_is_404(client):
    assert client.post("/v1/projects/nope/deepdive/frame",
                       json={"topic": "x"}).status_code == 404

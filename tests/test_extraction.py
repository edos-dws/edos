"""Auto-context extraction (heuristic fallback under the stub LLM) + smart-ask endpoint."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import extraction


def test_heuristic_extracts_requirements_and_assumptions():
    items = extraction.extract(
        "The device must measure pH and TDS; battery is 18650; BOM under 12 USD; "
        "I assume the sensors are analog"
    )
    types = {i["type"] for i in items}
    contents = " ".join(i["content"].lower() for i in items)
    assert "requirement" in types
    assert "assumption" in types           # "I assume the sensors are analog"
    assert "ph" in contents and "bom" in contents


def test_extract_returns_valid_types_only():
    for it in extraction.extract("must support BLE and CAN; assume automotive temp"):
        assert it["type"] in {"requirement", "decision", "assumption", "document"}


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_smart_ask_extracts_context_then_reasons(client):
    pid = client.post("/v1/projects", json={"name": "WQ"}).json()["id"]
    # project starts EMPTY — the engineer just asks; EDOS should bootstrap context from the question
    r = client.post(f"/v1/projects/{pid}/ask", json={
        "question": "Which MCU for a device that must measure pH and DO on an 18650 battery under $12 BOM?"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["extracted"]                       # context was auto-captured
    assert body["decision"]["status"] in {"recommended", "needs_clarification"}
    # extracted items are now real project context
    items = client.get(f"/v1/projects/{pid}/items").json()
    assert len(items) == len(body["extracted"])


def test_smart_ask_missing_project_404(client):
    assert client.post("/v1/projects/nope/ask", json={"question": "x"}).status_code == 404

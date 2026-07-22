"""WebSocket streaming + live event delivery + health/CORS (live-connectivity layer)."""
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.models.decision import validate_against_contract

client = TestClient(app)


def _cand(ref, content):
    return {"type": "requirement", "ref_id": ref, "content": content,
            "signals": {"graph": 0.9, "semantic": 0.9, "recency": 0.9, "confidence": 0.9, "focus": 0.9}}


def test_health():
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/v1/health").json()["status"] == "ok"


def test_ws_analyze_streams_stages_then_decision():
    with client.websocket_connect("/v1/ws/analyze") as ws:
        ws.send_json({"project_id": "p1", "question": "pick an MCU", "context_items": [_cand("R1", "LoRaWAN")]})
        types, decision = [], None
        while True:
            m = ws.receive_json()
            types.append(m["type"])
            if m["type"] == "decision":
                decision = m["decision"]
            if m["type"] == "done":
                break
        assert "stage" in types and "decision" in types
        validate_against_contract(decision)


def test_ws_analyze_streams_clarification_on_empty_context():
    with client.websocket_connect("/v1/ws/analyze") as ws:
        ws.send_json({"project_id": "p1", "question": "?", "context_items": []})
        seen = set()
        while True:
            m = ws.receive_json()
            seen.add(m["type"])
            if m["type"] == "done":
                break
        assert "clarification" in seen


def test_ws_events_connects_and_delivers_published_event():
    with client.websocket_connect("/v1/ws/projects/p9/events") as ws:
        assert ws.receive_json() == {"type": "connected", "project_id": "p9"}
        # publish via REST -> should arrive on the live stream
        r = client.post("/v1/projects/p9/events", json={"type": "alert", "message": "check duty cycle"})
        assert r.json()["delivered"] == 1
        event = ws.receive_json()
        assert event["type"] == "alert"


def test_publish_with_no_subscribers_delivers_zero():
    assert client.post("/v1/projects/empty/events", json={"type": "x"}).json()["delivered"] == 0

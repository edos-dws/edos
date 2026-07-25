"""UI-CP-0 — the workspace shell (Project Brain, not a chat app) is served and self-contained."""
from fastapi.testclient import TestClient

from edos.api.app import app

client = TestClient(app)


def test_app_shell_served():
    r = client.get("/app")
    assert r.status_code == 200
    body = r.text
    assert "EDOS" in body
    assert "PROJECT BRAIN" in body            # Project Brain workspace, not chat
    assert "Engineering Review" in body        # mode tabs present
    assert "Deep Dive" in body
    assert "<script" in body                   # self-contained SPA
    assert "qbubble" not in body               # chat paradigm removed

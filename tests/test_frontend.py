"""CP-18 — the default UI is served and self-contained."""
from fastapi.testclient import TestClient

from edos.api.app import app

client = TestClient(app)


def test_app_page_served():
    r = client.get("/app")
    assert r.status_code == 200
    assert "EDOS" in r.text
    assert "/v1/analyze" in r.text          # wired to the API
    assert "<script" in r.text              # self-contained SPA

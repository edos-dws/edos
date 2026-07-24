"""CP-10 — project & conversation REST endpoints (TestClient over the real store, test DB session)."""
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


def test_project_lifecycle_endpoints(client):
    # create
    r = client.post("/v1/projects", json={"name": "Water Quality", "domain": "embedded"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["name"] == "Water Quality"

    # list + get
    assert any(p["id"] == pid for p in client.get("/v1/projects").json())
    assert client.get(f"/v1/projects/{pid}").json()["domain"] == "embedded"

    # patch
    r = client.patch(f"/v1/projects/{pid}", json={"name": "WQ v2"})
    assert r.json()["name"] == "WQ v2"

    # delete
    assert client.delete(f"/v1/projects/{pid}").status_code == 200
    assert client.get(f"/v1/projects/{pid}").status_code == 404


def test_missing_project_is_404(client):
    assert client.get("/v1/projects/nope").status_code == 404
    assert client.patch("/v1/projects/nope", json={"name": "x"}).status_code == 404
    assert client.delete("/v1/projects/nope").status_code == 404


def test_conversation_endpoints(client):
    pid = client.post("/v1/projects", json={"name": "X"}).json()["id"]

    r = client.post(f"/v1/projects/{pid}/conversations", json={"title": "MCU selection"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["project_id"] == pid

    assert any(c["id"] == cid for c in client.get(f"/v1/projects/{pid}/conversations").json())

    got = client.get(f"/v1/conversations/{cid}").json()
    assert got["id"] == cid
    assert got["turns"] == []


def test_conversation_on_missing_project_is_404(client):
    assert client.post("/v1/projects/nope/conversations", json={"title": "t"}).status_code == 404
    assert client.get("/v1/conversations/nope").status_code == 404

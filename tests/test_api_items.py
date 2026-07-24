"""CP-12 — project item ingestion endpoint."""
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


def test_ingest_and_list_items(client):
    pid = client.post("/v1/projects", json={"name": "WQ"}).json()["id"]

    r = client.post(f"/v1/projects/{pid}/items",
                    json={"id": "REQ-1", "item_type": "requirement", "content": "Read pH sensor"})
    assert r.status_code == 201
    assert r.json()["needs_linking"] is True  # first item

    r2 = client.post(f"/v1/projects/{pid}/items",
                     json={"id": "DEC-1", "item_type": "decision",
                           "content": "This depends on REQ-1"})
    assert r2.json()["needs_linking"] is False  # linked via reference

    ids = {i["id"] for i in client.get(f"/v1/projects/{pid}/items").json()}
    assert ids == {"REQ-1", "DEC-1"}


def test_ingest_on_missing_project_404(client):
    assert client.post("/v1/projects/nope/items",
                       json={"item_type": "requirement", "content": "x"}).status_code == 404

"""CP-20 — domain procedural-memory rules + proactive watchdog."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import domain, ingestion, watchdog


def test_domain_rules_flag_known_patterns():
    flags = {f.key for f in domain.apply_rules([
        "Read pH sensor with nA-level DO current",
        "Battery 18650 always-on device",
    ])}
    assert "high-impedance-afe" in flags
    assert "power-budget" in flags


def test_domain_rules_no_false_flags():
    assert domain.apply_rules(["quarterly financial report about revenue"]) == []


def test_watchdog_flags_conflict_and_invalidated_dependency(session):
    ingestion.ingest_item(session, id="DEC-1", project_id="p1", item_type="decision", content="use ESP32")
    ingestion.ingest_item(session, id="DEC-2", project_id="p1", item_type="decision",
                          content="this supersedes DEC-1, use nRF52")            # DEC-1 -> superseded
    ingestion.ingest_item(session, id="DEC-3", project_id="p1", item_type="decision",
                          content="firmware plan depends on DEC-1")              # depends on a superseded item

    alerts = watchdog.scan(session, "p1")
    types = {a.type for a in alerts}
    assert "stale_item" in types                 # DEC-1 superseded
    assert "invalidated_dependency" in types     # DEC-3 depends on superseded DEC-1


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_alerts_and_ruleflags_endpoints(client):
    pid = client.post("/v1/projects", json={"name": "WQ"}).json()["id"]
    client.post(f"/v1/projects/{pid}/items",
                json={"id": "REQ-1", "item_type": "requirement",
                      "content": "measure pH with high-impedance electrode, battery 18650"})
    flags = client.get(f"/v1/projects/{pid}/rule-flags").json()
    assert any(f["key"] == "high-impedance-afe" for f in flags)
    assert client.get(f"/v1/projects/{pid}/alerts").status_code == 200
    assert client.get("/v1/projects/nope/alerts").status_code == 404

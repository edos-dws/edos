"""CP-17 — feedback / learning loop: outcome capture + calibration."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import decision_store, feedback
from edos.models.decision import Decision


def _persist(session, did, confidence):
    d = Decision(summary="s", recommendation="r", confidence=confidence, status="recommended",
                 evidence=[{"claim": "c", "source": "REQ-1", "kind": "fact"}])
    return decision_store.save_new(session, id=did, project_id="p1", decision=d)


def test_record_outcome_snapshots_confidence(session):
    _persist(session, "D-1", 0.9)
    row = feedback.record_outcome(session, decision_id="D-1", outcome="accepted")
    assert row.confidence_at_outcome == 0.9


def test_record_outcome_rejects_bad_value(session):
    _persist(session, "D-1", 0.9)
    with pytest.raises(ValueError):
        feedback.record_outcome(session, decision_id="D-1", outcome="banana")


def test_record_outcome_missing_decision_none(session):
    assert feedback.record_outcome(session, decision_id="nope", outcome="accepted") is None


def test_calibration_gap(session):
    _persist(session, "D-1", 0.9)
    _persist(session, "D-2", 0.3)
    feedback.record_outcome(session, decision_id="D-1", outcome="accepted")   # high-conf held up
    feedback.record_outcome(session, decision_id="D-2", outcome="reversed")   # low-conf reversed
    session.commit()
    rep = feedback.calibration_report(session)
    assert rep["mean_confidence_accepted"] == 0.9
    assert rep["mean_confidence_reversed"] == 0.3
    assert rep["calibration_gap"] == pytest.approx(0.6)  # well-calibrated


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_outcome_and_calibration_endpoints(client):
    did = client.post("/v1/decisions", json={
        "project_id": "p1",
        "decision": {"schema_version": "edos.decision.v1", "summary": "s", "recommendation": "r",
                     "confidence": 0.8, "status": "recommended",
                     "evidence": [{"claim": "c", "source": "REQ-1", "kind": "fact"}]},
    }).json()["id"]
    assert client.post(f"/v1/decisions/{did}/outcome", json={"outcome": "accepted"}).status_code == 200
    rep = client.get("/v1/calibration").json()
    assert rep["n"] == 1
    assert "ranking_suggestion" in rep

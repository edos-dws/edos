"""CP-16 — verification hardening (faithfulness-aware) + freeze gate (disabled, fail-safe)."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import decision_store
from edos.engines.verification import VerificationEngine
from edos.models.decision import Decision


def _decision(**over):
    base = {"summary": "s", "recommendation": "r", "confidence": 0.8, "status": "recommended",
            "evidence": [{"claim": "c", "source": "REQ-1", "kind": "fact"}]}
    base.update(over)
    return Decision(**base)


def test_verify_flags_ungrounded_evidence_with_context():
    d = _decision(evidence=[{"claim": "hallucinated", "source": "GHOST", "kind": "fact"}])
    v = VerificationEngine().verify(d, context_refs=["REQ-1"])
    assert v.agreement is False
    assert v.faithfulness == 0.0
    assert any("ungrounded" in i for i in v.issues)


def test_verify_without_context_is_structural_only():
    v = VerificationEngine().verify(_decision())
    assert v.faithfulness is None      # no faithfulness pass unless context given


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_freeze_is_refused_while_threshold_unset(client, session):
    d = _decision(status="verified", freeze_blockers=[])
    row = decision_store.save_new(session, id="D-1", project_id="p1", decision=d, status="verified")
    session.commit()
    r = client.post(f"/v1/decisions/{row.id}/freeze", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["frozen"] is False                                  # no autonomous freeze
    assert any("threshold" in reason for reason in body["reasons"])  # T unset


def test_freeze_missing_decision_404(client):
    assert client.post("/v1/decisions/nope/freeze", json={}).status_code == 404

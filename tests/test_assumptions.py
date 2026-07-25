"""UI-CP-6 — first-class assumptions + lifecycle.

Covers the engine (per-project A-ids, dedupe, status transitions), the persist→mirror wiring, the resolution
engine keeping the ledger in step, the endpoints, and the now-live `/brain` assumptions count.
"""
from fastapi.testclient import TestClient

from edos.api import app as app_module
from edos.api.deps import get_session
from edos.engines import assumptions, decision_store, resolution
from edos.models.decision import Decision


def _decision(summary="Use ESP32-C6", statements=("ADC is 12-bit accurate", "Ambient stays below 60C")):
    return Decision(
        summary=summary, recommendation=f"Adopt for {summary}", confidence=0.7, status="recommended",
        assumptions=[{"statement": s, "confidence": 0.6, "risk_if_wrong": f"{s} may be false"}
                     for s in statements],
        evidence=[{"claim": "cheap", "source": "REQ-5", "kind": "fact"}],
    )


# ---------------- engine ----------------
def test_next_aid_is_per_project_and_sequential(session):
    a1 = assumptions.create(session, "p1", "Battery is LFP")
    a2 = assumptions.create(session, "p1", "Pack is 14s")
    b1 = assumptions.create(session, "p2", "Different project assumption")
    assert (a1.id, a2.id) == ("A1", "A2")
    assert b1.id == "A1"  # per-project — A-ids reset per project


def test_create_dedupes_on_statement_case_insensitive(session):
    a1 = assumptions.create(session, "p1", "Ambient stays below 60C", source_decision_id="D-1")
    a2 = assumptions.create(session, "p1", "  ambient stays BELOW 60c ", risk_if_wrong="overheats")
    assert a2.row_id == a1.row_id  # same row
    assert len(assumptions.list_for_project(session, "p1")) == 1
    assert a2.source_decision_id == "D-1"       # backfilled, not duplicated
    assert a2.risk_if_wrong == "overheats"      # backfilled


def test_set_status_transitions(session):
    a = assumptions.create(session, "p1", "X holds")
    assert a.status == "created"
    updated = assumptions.set_status(session, aid=a.id, status="validated", project_id="p1")
    assert updated.status == "validated"


def test_upsert_from_decision_mirrors_inline_assumptions(session):
    rows = assumptions.upsert_from_decision(session, "p1", _decision(), "D-9")
    assert [r.id for r in rows] == ["A1", "A2"]
    assert all(r.status == "created" and r.source_decision_id == "D-9" for r in rows)


# ---------------- resolution keeps the ledger in step ----------------
def test_challenge_and_resolve_update_first_class_status(session):
    decision_store.save_new(session, id="D-1", project_id="p1", decision=_decision())
    assumptions.upsert_from_decision(session, "p1", _decision(), "D-1")

    resolution.challenge_assumption(session, decision_id="D-1", statement="ADC is 12-bit accurate")
    resolution.resolve_assumption(session, decision_id="D-1", statement="Ambient stays below 60C",
                                  resolution="measured 45C on bench")
    session.commit()

    by_stmt = {a.statement: a.status for a in assumptions.list_for_project(session, "p1")}
    assert by_stmt["ADC is 12-bit accurate"] == "challenged"
    assert by_stmt["Ambient stays below 60C"] == "validated"


# ---------------- endpoints + brain ----------------
def _client(session):
    app_module.app.dependency_overrides[get_session] = lambda: session
    return TestClient(app_module.app)


def test_endpoints_and_brain_count_live(session):
    client = _client(session)
    try:
        pid = client.post("/v1/projects", json={"name": "BMS"}).json()["id"]

        # brain starts at 0 assumptions (the old hardcoded 0 is now a real, live count)
        assert client.get(f"/v1/projects/{pid}/brain").json()["counts"]["assumptions"] == 0

        env = client.post("/v1/decisions", json={"project_id": pid, "decision": _decision().to_contract_dict()})
        assert env.status_code == 201

        listed = client.get(f"/v1/projects/{pid}/assumptions").json()
        assert [a["id"] for a in listed] == ["A1", "A2"]
        assert all(a["status"] == "created" for a in listed)

        brain = client.get(f"/v1/projects/{pid}/brain").json()["counts"]
        assert brain["assumptions"] == 2 and brain["assumptions_open"] == 2

        # transition A1 → challenged
        r = client.post("/v1/assumptions/A1/status", json={"status": "challenged", "project_id": pid})
        assert r.status_code == 200 and r.json()["status"] == "challenged"

        brain = client.get(f"/v1/projects/{pid}/brain").json()["counts"]
        assert brain["assumptions"] == 2 and brain["assumptions_resolved"] == 1

        # invalid status rejected; unknown aid 404s
        assert client.post("/v1/assumptions/A1/status", json={"status": "bogus"}).status_code == 422
        assert client.post("/v1/assumptions/A99/status",
                           json={"status": "validated", "project_id": pid}).status_code == 404
    finally:
        app_module.app.dependency_overrides.pop(get_session, None)

"""UI-CP-11 — Adaptive Context-Grounded Clarification.

Deep Dive v2 makes questioning (a) **context-grounded** — a question whose concern is already established in
the project is SKIPPED, not asked — and (b) **adaptive** — after the batch answers, 0–2 targeted follow-ups
fire only when an answer reveals a real gap/contradiction. These tests run offline via the stub provider
(heuristic fallback + deterministic contradiction check), so they are deterministic.
"""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import decision_store, deepdive, ingestion
from edos.models.decision import Decision

BMS_TOPIC = "Cell balancing strategy — passive vs active for a 14S LFP pack, cost is a priority"

IMBALANCE_Q = "Maximum acceptable cell imbalance at end of life?"


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _passive_balancing_decision(session, project_id: str) -> None:
    """Persist a stored decision that commits to *passive* cell balancing."""
    dec = Decision(
        summary="Use passive balancing for the pack",
        recommendation="Adopt passive cell balancing to keep cost down",
        confidence=0.6, status="recommended",
        evidence=[{"claim": "cost priority", "source": "test", "kind": "fact"}],
    )
    decision_store.save_new(session, id="d-balancing", project_id=project_id, decision=dec,
                            status="recommended")


# ---- (a) a question is SKIPPED when its concern is already in the project context ----
def test_question_skipped_when_concern_already_known(session):
    pid = "p-v2-skip"
    # ingest an item that already answers the "cell imbalance at end of life" concern
    ingestion.ingest_item(
        session, id="ctx-imb", project_id=pid, item_type="requirement",
        content=("The maximum acceptable end-of-life cell imbalance for the 14S LFP pack is under "
                 "5 percent across the pack."),
    )
    plan = deepdive.plan_questions(session, pid, BMS_TOPIC)

    kept_qs = {q["q"] for q in plan["questions"]}
    skipped_qs = {s["q"] for s in plan["skipped"]}

    assert IMBALANCE_Q in skipped_qs           # the answered concern is skipped …
    assert IMBALANCE_Q not in kept_qs          # … and NOT re-asked
    assert plan["questions"]                    # other, still-open questions remain
    # the skip carries a human-readable reason quoting the covering context
    reason = next(s["reason"] for s in plan["skipped"] if s["q"] == IMBALANCE_Q)
    assert "already established" in reason


# ---- (b) a follow-up fires when an answer contradicts a stored decision ----
def test_followup_fires_on_contradiction(session):
    pid = "p-v2-contra"
    _passive_balancing_decision(session, pid)
    answers = [{"id": "q1", "answer": "We will use active balancing to handle the cell spread"}]

    fus = deepdive.follow_up(session, pid, BMS_TOPIC, answers)

    assert 1 <= len(fus) <= 2                    # 0–2 follow-ups, cap 2
    assert all({"id", "q", "why"} == set(f) for f in fus)
    # the follow-up names the conflict with the stored (passive) decision
    joined = " ".join(f["q"].lower() + " " + f["why"].lower() for f in fus)
    assert "balancing" in joined
    assert "passive" in joined and "active" in joined


# ---- (c) no follow-up when answers are consistent ----
def test_no_followup_when_consistent(session):
    pid = "p-v2-consistent"
    _passive_balancing_decision(session, pid)
    answers = [{"id": "q1", "answer": "Passive balancing is fine and keeps the BOM cheap"}]

    fus = deepdive.follow_up(session, pid, BMS_TOPIC, answers)
    assert fus == []                            # consistent answer → ready to decide


# ---- (d) offline fallback still returns questions ----
def test_offline_fallback_returns_questions(session):
    pid = "p-v2-empty"
    plan = deepdive.plan_questions(session, pid, "Thermal design for a 100A power stage with forced-air")
    assert 5 <= len(plan["questions"]) <= 8      # heuristic probes fire offline
    assert plan["skipped"] == []                 # empty project → nothing already known
    assert plan["note"] == ""                    # not "fully covered"


# ---- endpoints ----
def test_followup_endpoint_and_404(client):
    pid = client.post("/v1/projects", json={"name": "BMS"}).json()["id"]
    # consistent (no stored decision) → empty follow-ups, ready to decide
    r = client.post(f"/v1/projects/{pid}/deepdive/followup",
                    json={"topic": BMS_TOPIC, "answers": [{"id": "q1", "answer": "passive balancing"}]})
    assert r.status_code == 200
    assert r.json() == {"questions": []}
    # missing project → 404
    assert client.post("/v1/projects/nope/deepdive/followup",
                       json={"topic": "x", "answers": []}).status_code == 404


def test_deepdive_endpoint_reports_skipped(client):
    pid = client.post("/v1/projects", json={"name": "BMS"}).json()["id"]
    # ingest context that answers the imbalance concern, then ask on a related topic
    client.post(f"/v1/projects/{pid}/items",
                json={"content": ("The maximum acceptable end-of-life cell imbalance for the 14S LFP pack "
                                  "is under 5 percent across the pack."),
                      "item_type": "requirement"})
    body = client.post(f"/v1/projects/{pid}/deepdive", json={"topic": BMS_TOPIC}).json()
    assert IMBALANCE_Q in {s["q"] for s in body["skipped"]}
    assert IMBALANCE_Q not in {q["q"] for q in body["questions"]}

"""UI-CP-4 — Deep Dive → Decision Card.

Deep Dive asks 5-8 targeted questions (each with a WHY rationale), then produces a rich Decision Card whose
extra fields live in the persistence ENVELOPE (`decision_detail`), NOT the locked `edos.decision.v1`
contract. These tests run offline via the stub provider (heuristic fallback), so they are deterministic.
"""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import deepdive
from edos.models.decision import Decision, validate_against_contract

DETAIL_REQUIRED = {"comparison_matrix", "decision_impact", "impacted_components", "review_conditions"}

BMS_TOPIC = "Cell balancing strategy — passive vs active for a 14S LFP pack, cost is a priority"


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _new_project(client) -> str:
    return client.post("/v1/projects", json={"name": "BMS"}).json()["id"]


# ---- stage 1: targeted questions with WHY (UI-CP-11: signature is (session, project_id, topic)) ----
def test_plan_questions_shape_and_count(session):
    plan = deepdive.plan_questions(session, "p-plan-1", BMS_TOPIC)
    assert set(plan) == {"questions", "skipped", "note"}
    qs = plan["questions"]
    assert plan["skipped"] == []                    # empty project → nothing already known
    assert 5 <= len(qs) <= 8
    ids = set()
    for q in qs:
        assert set(q) == {"id", "q", "why"}
        assert q["q"] and q["why"]                 # every question carries its rationale
        ids.add(q["id"])
    assert len(ids) == len(qs)                      # ids are unique


def test_plan_questions_are_topic_targeted(session):
    qs = deepdive.plan_questions(session, "p-plan-2", BMS_TOPIC)["questions"]
    joined = " ".join(q["q"].lower() for q in qs)
    # balancing/cost topic should surface the imbalance + cost questions (deterministic probes)
    assert "imbalance" in joined
    assert "cost" in joined


def test_deepdive_endpoint(client):
    pid = _new_project(client)
    body = client.post(f"/v1/projects/{pid}/deepdive", json={"topic": BMS_TOPIC}).json()
    assert body["topic"] == BMS_TOPIC
    assert body["skipped"] == []                    # empty project → no "already known"
    assert 5 <= len(body["questions"]) <= 8
    assert all({"id", "q", "why"} == set(q) for q in body["questions"])


def test_deepdive_missing_project_404(client):
    assert client.post("/v1/projects/nope/deepdive", json={"topic": "x"}).status_code == 404
    assert client.post("/v1/projects/nope/deepdive/decide",
                       json={"topic": "x", "answers": []}).status_code == 404


# ---- stage 2: the Decision Card ----
def test_decide_returns_contract_valid_decision_and_detail(session):
    pid = "p-decide"
    # decide() reasons over retriever context (empty here) + answers
    answers = [{"id": "q1", "answer": "End-of-life imbalance under 5%"},
               {"id": "q2", "answer": "Balance during CC/CV charging only"}]
    decision, detail = deepdive.decide(session, pid, BMS_TOPIC, answers)

    # the core decision is a contract-valid edos.decision.v1
    assert isinstance(decision, Decision)
    validate_against_contract(decision.to_contract_dict())
    assert decision.status == "recommended"        # engine never emits verified/frozen

    # the rich detail carries the four required Decision-Card blocks
    assert DETAIL_REQUIRED <= set(detail)
    cm = detail["comparison_matrix"]
    assert cm["criteria"] and cm["options"]
    assert sum(1 for o in cm["options"] if o["recommended"]) == 1   # exactly one ★ recommended column
    for o in cm["options"]:
        assert len(o["values"]) == len(cm["criteria"])             # matrix is rectangular
    assert all({"area", "change"} == set(x) for x in detail["decision_impact"])
    assert detail["impacted_components"]


def test_detail_fields_are_not_in_locked_contract(session):
    """The rich fields must NOT leak into the locked contract dict (additionalProperties:false)."""
    decision, _ = deepdive.decide(session, "p1", BMS_TOPIC, [])
    body = decision.to_contract_dict()
    for k in ("comparison_matrix", "decision_impact", "impacted_components", "review_conditions"):
        assert k not in body
    validate_against_contract(body)                # still contract-valid


def test_decide_endpoint_persists_and_returns_envelope(client):
    pid = _new_project(client)
    r = client.post(f"/v1/projects/{pid}/deepdive/decide",
                    json={"topic": BMS_TOPIC,
                          "answers": [{"id": "q1", "answer": "under 5% at EOL"}]})
    assert r.status_code == 201
    env = r.json()
    # envelope carries the persisted decision + the detail (in the envelope, not the contract)
    assert env["decision"]["schema_version"] == "edos.decision.v1"
    assert env["decision_detail"] is not None
    assert DETAIL_REQUIRED <= set(env["decision_detail"])
    validate_against_contract(env["decision"])

    # it was actually persisted and is fetchable with the detail intact
    got = client.get(f"/v1/decisions/{env['id']}").json()
    assert got["decision_detail"]["comparison_matrix"]["options"]


def test_accept_carries_detail_forward(client):
    pid = _new_project(client)
    env = client.post(f"/v1/projects/{pid}/deepdive/decide",
                      json={"topic": BMS_TOPIC, "answers": []}).json()
    acc = client.post(f"/v1/decisions/{env['id']}/accept", json={}).json()
    assert acc["status"] == "accepted"
    assert acc["version"] == env["version"] + 1
    # the rich detail survives the new (accepted) version
    assert acc["decision_detail"] is not None
    assert DETAIL_REQUIRED <= set(acc["decision_detail"])


def test_related_decisions_link_other_project_decisions(client):
    pid = _new_project(client)
    first = client.post(f"/v1/projects/{pid}/deepdive/decide",
                        json={"topic": "Power stage architecture", "answers": []}).json()
    second = client.post(f"/v1/projects/{pid}/deepdive/decide",
                         json={"topic": BMS_TOPIC, "answers": []}).json()
    related_ids = {r["id"] for r in second["decision_detail"]["related_decisions"]}
    assert first["id"] in related_ids              # the explorer surfaces the earlier decision

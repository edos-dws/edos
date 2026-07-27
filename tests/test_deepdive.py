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
    assert set(plan) == {"questions", "skipped", "note", "generated_by", "understanding"}
    qs = plan["questions"]
    assert plan["generated_by"] in {"llm", "heuristic"}   # offline stub → "heuristic"
    assert plan["skipped"] == []                    # empty project → nothing already known
    assert 1 <= len(qs) <= 5                         # need-driven, capped at 5 (never a forced quota)
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
    assert 1 <= len(body["questions"]) <= 5         # need-driven, capped at 5 (never a forced quota)
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


# ---- matrix criteria are derived from the topic, not a fixed template ----
def test_heuristic_card_carries_runner_up(session):
    """A degraded (LLM-offline) card must still be structurally complete: an A-vs-B decision names the
    runner-up it beat, derived from the matrix it already built — no fabricated specifics. Degraded != poorer
    than the contract (Step 7 parity in the fallback path)."""
    _, det = deepdive.decide(
        session, "p-ru", "Heatsink vs forced-air cooling for a 200W motor driver",
        [{"id": "q1", "answer": "thermal dissipation budget is tight"}],
    )
    opts = det["comparison_matrix"]["options"]
    assert len(opts) >= 2, "an A-vs-B topic should yield a 2+ option matrix"
    ru = det.get("runner_up")
    assert ru and ru["option"] == opts[1]["name"], "runner-up must be the #2 (non-recommended) option"
    assert ru["tipped_by"], "runner-up must say what tipped the decision away from it"


def test_heuristic_matrix_criteria_are_topic_derived(session):
    """The comparison-matrix ROWS must reflect what the decision is about — a thermal/safety topic surfaces
    thermal + safety axes, a cost/accuracy topic surfaces those — so no two unrelated cards read identically."""
    _, thermal = deepdive.decide(
        session, "p-th", "Heatsink vs forced-air cooling for a 200W motor driver, junction temperature margin",
        [{"id": "q1", "answer": "thermal dissipation budget is tight, ISO 26262 ASIL-B applies"}],
    )
    crit_thermal = " ".join(thermal["comparison_matrix"]["criteria"]).lower()
    assert "thermal" in crit_thermal
    assert "safety" in crit_thermal or "compliance" in crit_thermal

    _, cost = deepdive.decide(
        session, "p-co", "Op-amp selection — precision vs cost for a 16-bit ADC front end",
        [{"id": "q1", "answer": "accuracy and drift matter, BOM cost target under $2"}],
    )
    crit_cost = " ".join(cost["comparison_matrix"]["criteria"]).lower()
    assert "accuracy" in crit_cost or "precision" in crit_cost
    assert "cost" in crit_cost
    # the two cards must NOT share an identical criteria set (the old fixed-template bug)
    assert thermal["comparison_matrix"]["criteria"] != cost["comparison_matrix"]["criteria"]


# ---- Revise Decision → a new, sharper version of the same lineage ----
def test_revise_creates_new_version_of_same_decision(client):
    pid = _new_project(client)
    env = client.post(f"/v1/projects/{pid}/deepdive/decide",
                      json={"topic": BMS_TOPIC, "answers": [{"id": "q1", "answer": "under 5% at EOL"}]}).json()
    assert env["version"] == 1
    rev = client.post(f"/v1/decisions/{env['id']}/revise",
                      json={"instruction": "Cost target moved to under $1.50 per unit at 20k volume"})
    assert rev.status_code == 201
    body = rev.json()
    assert body["id"] == env["id"]                       # same decision lineage
    assert body["version"] == env["version"] + 1         # new immutable version
    assert body["parent_version"] == env["version"]
    assert body["status"] == "recommended"
    validate_against_contract(body["decision"])
    assert DETAIL_REQUIRED <= set(body["decision_detail"])
    # the prior version is still fetchable (immutability)
    hist = client.get(f"/v1/decisions/{env['id']}/history").json()
    assert {h["version"] for h in hist} >= {1, 2}


def test_revise_requires_instruction(client):
    pid = _new_project(client)
    env = client.post(f"/v1/projects/{pid}/deepdive/decide",
                      json={"topic": BMS_TOPIC, "answers": []}).json()
    assert client.post(f"/v1/decisions/{env['id']}/revise", json={"instruction": "   "}).status_code == 422


def test_revise_missing_decision_404(client):
    assert client.post("/v1/decisions/nope/revise",
                       json={"instruction": "tighten the spec"}).status_code == 404


def test_related_decisions_link_other_project_decisions(client):
    pid = _new_project(client)
    first = client.post(f"/v1/projects/{pid}/deepdive/decide",
                        json={"topic": "Power stage architecture", "answers": []}).json()
    second = client.post(f"/v1/projects/{pid}/deepdive/decide",
                         json={"topic": BMS_TOPIC, "answers": []}).json()
    related_ids = {r["id"] for r in second["decision_detail"]["related_decisions"]}
    assert first["id"] in related_ids              # the explorer surfaces the earlier decision


def test_continuous_reasoning_flow_until_accept(client):
    """THE flow the tool is built around: EDOS reasons WITH the engineer (reasoning-first frame → targeted
    questions → a decision), and the decision stays a re-reasonable PROPOSAL — it only crystallizes when the
    engineer ACCEPTS. This end-to-end test locks that contract so no future change silently makes the card a
    one-shot verdict again."""
    pid = _new_project(client)
    topic = BMS_TOPIC

    # 1. REASONING-FIRST FRAME — reflected back BEFORE any card (understanding + lenses it will reason with)
    frame = client.post(f"/v1/projects/{pid}/deepdive/frame", json={"topic": topic}).json()
    assert frame["understanding"]
    assert "lenses" in frame and "spine" in frame

    # 2. TARGETED QUESTIONS — reasoning before deciding (need-driven; may be empty, but the stage exists)
    q = client.post(f"/v1/projects/{pid}/deepdive", json={"topic": topic}).json()
    assert "questions" in q

    # 3. DECIDE → a PROPOSAL, explicitly NOT final
    env = client.post(f"/v1/projects/{pid}/deepdive/decide",
                      json={"topic": topic, "answers": [{"id": "q1", "answer": "under 5% spread at EOL"}]}).json()
    assert env["version"] == 1
    assert env["status"] == "recommended"        # a proposal — NOT accepted
    did = env["id"]

    # 4. CONTINUOUS RE-REASONING — revise any number of times; each a new immutable version, still a proposal
    r1 = client.post(f"/v1/decisions/{did}/revise",
                     json={"instruction": "Cost target moved to under $1.50 at 20k volume"}).json()
    assert r1["version"] == 2 and r1["status"] == "recommended"
    r2 = client.post(f"/v1/decisions/{did}/revise",
                     json={"instruction": "Must also pass CISPR 25 class 5"}).json()
    assert r2["version"] == 3 and r2["status"] == "recommended"   # STILL a proposal after two re-reasons

    # the full reasoning trail is kept immutable (every version fetchable)
    hist = client.get(f"/v1/decisions/{did}/history").json()
    assert {h["version"] for h in hist} >= {1, 2, 3}

    # 5. ACCEPT → crystallize: only now is it final
    acc = client.post(f"/v1/decisions/{did}/accept", json={}).json()
    assert acc["status"] == "accepted"
    out = client.post(f"/v1/decisions/{did}/outcome", json={"outcome": "accepted"}).json()
    assert out["outcome"] == "accepted"

"""UI-CP-5 — Challenge My Decision (the iconic interaction, PDF p11).

EDOS argues AGAINST its own recommendation: it names the single load-bearing assumption, shows what that
assumption is costing vs what the alternative offers, and a cost callout. Marking it *challenged* flips the
assumption into a monitored risk. These tests run offline via the stub provider (heuristic fallback), so they
are deterministic — and assert that offline we NEVER fabricate dollar figures.
"""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import challenge as challenge_engine
from edos.models.decision import Decision, validate_against_contract


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _decision(**over) -> dict:
    """A BMS-flavoured recommended decision that HAS assumptions + tradeoffs to challenge."""
    base = {
        "schema_version": "edos.decision.v1",
        "summary": "Integrate a gate driver for the 28S expansion — recommend ADBMS6830 + BQ76200",
        "recommendation": ("Recommend ADBMS6830 with an external BQ76200 gate driver, sized for the 28S "
                           "expansion path."),
        "confidence": 0.6,
        "status": "recommended",
        "assumptions": [
            {"statement": "The pack will expand to 28S", "confidence": 0.35,
             "risk_if_wrong": "If it stays 14S the gate-driver IC and its firmware are wasted BOM"},
            {"statement": "Forced-air cooling is available in the enclosure", "confidence": 0.7,
             "risk_if_wrong": "Sealed enclosure forces derating"},
            {"statement": "isoSPI noise environment is benign", "confidence": 0.8},
        ],
        "risks": [
            {"description": "ADBMS6830 has no integrated gate drivers; MOSFETs cannot switch without one",
             "severity": "high", "likelihood": "medium", "mitigation": "Add BQ76200"},
        ],
        "tradeoffs": [
            {"option": "ADBMS6830 + BQ76200", "benefit": "Scales to 28S without a respin",
             "drawback": "Extra IC + firmware + BOM cost carried on every unit"},
            {"option": "Integrated-driver AFE", "benefit": "Lower BOM and firmware for a 14S-only design",
             "drawback": "Caps the design at 14S — a respin if the pack ever grows"},
        ],
        "evidence": [{"claim": "gate driver needed", "source": "Infineon AN-2013-02", "kind": "external"}],
    }
    base.update(over)
    return base


def _persist(client, decision: dict) -> str:
    pid = client.post("/v1/projects", json={"name": "BMS"}).json()["id"]
    return client.post("/v1/decisions", json={"project_id": pid, "decision": decision}).json()["id"]


# ---- load-bearing assumption selection ----
def test_load_bearing_picks_lowest_confidence_biased_by_risk():
    d = Decision(**_decision())
    a = challenge_engine.load_bearing_assumption(d)
    # the 28S-expansion assumption is both lowest-confidence AND has the most severe risk_if_wrong
    assert a is not None
    assert a.statement == "The pack will expand to 28S"


def test_load_bearing_none_when_no_assumptions():
    d = Decision(**_decision(assumptions=[]))
    assert challenge_engine.load_bearing_assumption(d) is None


# ---- the challenge payload (offline heuristic) ----
def test_challenge_engine_shape_and_no_fabricated_dollars():
    d = Decision(**_decision())
    out = challenge_engine.challenge(d)
    assert set(out) >= {"assumption", "this_costs", "alternative_offers", "cost_callout", "alternative"}
    assert out["assumption"]["statement"] == "The pack will expand to 28S"
    assert out["this_costs"] and out["alternative_offers"]
    assert all(isinstance(x, str) and x for x in out["this_costs"])
    assert all(isinstance(x, str) and x for x in out["alternative_offers"])
    # the alternative is the OTHER tradeoff option
    assert out["alternative"] == "Integrated-driver AFE"
    # offline: no fabricated dollar figures anywhere (the decision states none)
    blob = " ".join(out["this_costs"] + out["alternative_offers"] + [out["cost_callout"]])
    assert "$" not in blob


def test_challenge_quotes_existing_figures_only():
    # when the engineer HAS put a dollar figure in the decision, the callout may reference it
    d = Decision(**_decision(
        summary="Gate driver for 28S — recurring $6/unit BOM adder",
        recommendation="Recommend ADBMS6830 + BQ76200 despite the $6/unit cost."))
    out = challenge_engine.challenge(d)
    assert "$6" in out["cost_callout"]


# ---- endpoints ----
def test_challenge_endpoint(client):
    did = _persist(client, _decision())
    r = client.post(f"/v1/decisions/{did}/challenge", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["decision_id"] == did
    assert body["assumption"]["statement"] == "The pack will expand to 28S"
    assert body["this_costs"] and body["alternative_offers"] and body["cost_callout"]


def test_challenge_404_and_422(client):
    assert client.post("/v1/decisions/nope/challenge", json={}).status_code == 404
    # a decision with no assumptions has nothing load-bearing to challenge
    did = _persist(client, _decision(assumptions=[]))
    assert client.post(f"/v1/decisions/{did}/challenge", json={}).status_code == 422


def test_mark_challenged_adds_monitored_risk(client):
    did = _persist(client, _decision())
    stmt = "The pack will expand to 28S"
    r = client.post(f"/v1/decisions/{did}/challenge/accept", json={"statement": stmt})
    assert r.status_code == 200
    env = r.json()
    # a new immutable version was appended
    assert env["version"] == 2
    decision = env["decision"]
    validate_against_contract(decision)
    # a monitored risk that names the challenged assumption now exists
    monitored = [rk for rk in decision["risks"] if "Challenged assumption (monitored)" in rk["description"]]
    assert len(monitored) == 1
    assert stmt in monitored[0]["description"]


def test_mark_challenged_is_idempotent(client):
    did = _persist(client, _decision())
    stmt = "The pack will expand to 28S"
    client.post(f"/v1/decisions/{did}/challenge/accept", json={"statement": stmt})
    env = client.post(f"/v1/decisions/{did}/challenge/accept", json={"statement": stmt}).json()
    monitored = [rk for rk in env["decision"]["risks"] if "Challenged assumption (monitored)" in rk["description"]]
    assert len(monitored) == 1  # not duplicated on a second challenge


def test_mark_challenged_404(client):
    assert client.post("/v1/decisions/nope/challenge/accept",
                       json={"statement": "x"}).status_code == 404

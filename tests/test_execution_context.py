"""UI-CP-9 — Execution Context (the handoff, PDF p24).

Engine-level tests (``engines.execution_context``) over a real session plus REST-surface tests via
TestClient. Everything is deterministic (no LLM, injected ``now``) so the gate stays green offline; DB tests
SKIP when Postgres is unreachable (see conftest).
"""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import assumptions as assumptions_engine
from edos.engines import decision_store, execution_context
from edos.engines.graph_builder import add_edge
from edos.models.decision import Decision
from edos.models.entities import RelationType
from edos.store import projects as store

UTC = dt.UTC


def _decision(summary, rec, *, assumptions=None, risks=None, next_actions=None,
              freeze_blockers=None, confidence=0.7):
    return Decision(
        summary=summary, recommendation=rec, confidence=confidence, status="recommended",
        assumptions=assumptions or [],
        risks=risks or [],
        next_actions=next_actions or [],
        freeze_blockers=freeze_blockers or [],
        evidence=[{"claim": "grounded", "source": "REQ-1", "kind": "fact"}],
    )


_DETAIL = {
    "comparison_matrix": {
        "criteria": ["Cost", "Accuracy"],
        "options": [
            {"name": "isoSPI daisy-chain", "values": ["Higher", "±2mV"], "recommended": True},
            {"name": "Discrete wiring", "values": ["Lower", "±10mV"], "recommended": False},
        ],
    },
    "recommendation": {"chosen": "isoSPI daisy-chain", "reasons": [], "eliminated": []},
    "decision_impact": [{"area": "Firmware", "change": "driver work"}],
    "impacted_components": ["AFE", "Comms"],
    "review_conditions": ["Revisit if cell count exceeds 14S"],
}


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------ engine: accepted decisions
def test_accepted_decision_is_included_with_key_params(session):
    pid = "proj-ec-1"
    decision_store.save_new(
        session, id="DEC-1", project_id=pid,
        decision=_decision("BMS cell monitoring topology", "Recommend isoSPI daisy-chain"),
        detail=_DETAIL,
    )
    decision_store.accept(session, "DEC-1")
    session.commit()

    ctx = execution_context.build(session, pid)
    ad = ctx["accepted_decisions"]
    assert len(ad) == 1
    assert ad[0]["id"] == "DEC-1"
    assert ad[0]["status"] == "accepted"
    assert ad[0]["provisional"] is False
    # key params derive from the recommended option's criteria + impacted components
    joined = " | ".join(ad[0]["key_params"])
    assert "Chosen option: isoSPI daisy-chain" in joined
    assert "Cost: Higher" in joined and "Accuracy: ±2mV" in joined
    assert "Impacted components: AFE, Comms" in joined
    assert ctx["meta"]["provisional"] is False


def test_no_accepted_falls_back_to_recommended_marked_provisional(session):
    pid = "proj-ec-prov"
    decision_store.save_new(session, id="DEC-R", project_id=pid,
                            decision=_decision("Thermal strategy", "Recommend forced-air"))
    session.commit()
    ctx = execution_context.build(session, pid)
    assert len(ctx["accepted_decisions"]) == 1
    assert ctx["accepted_decisions"][0]["provisional"] is True
    assert ctx["meta"]["provisional"] is True


# ------------------------------------------------------------------ engine: constraints
def test_constraints_from_requirements_review_conditions_and_risks(session):
    pid = "proj-ec-con"
    store_item(session, pid, "requirement", "The pack shall operate from -20C to 60C ambient", domain="Hardware")
    decision_store.save_new(
        session, id="DEC-C", project_id=pid,
        decision=_decision(
            "Cooling", "Recommend forced-air",
            risks=[{"description": "Sealed enclosure blocks airflow", "severity": "high",
                    "likelihood": "medium", "mitigation": "Add filtered vents"}],
        ),
        detail={"review_conditions": ["Revisit if IP rating is raised"]},
    )
    decision_store.accept(session, "DEC-C")
    session.commit()

    ctx = execution_context.build(session, pid)
    texts = [c["text"] for c in ctx["constraints"]]
    assert any("shall operate from -20C" in t for t in texts)
    assert any("Revisit if IP rating is raised" in t for t in texts)
    assert any("Sealed enclosure blocks airflow" in t and "filtered vents" in t for t in texts)


# ------------------------------------------------------------------ engine: interfaces
def test_interfaces_from_components_and_protocol_scan(session):
    pid = "proj-ec-if"
    store_item(session, pid, "requirement", "Cell monitor talks to the MCU over isoSPI; host bus is CAN")
    decision_store.save_new(
        session, id="DEC-IF", project_id=pid,
        decision=_decision("Comms", "Recommend isoSPI"),
        detail={"impacted_components": ["AFE", "Comms"]},
    )
    decision_store.accept(session, "DEC-IF")
    session.commit()

    ctx = execution_context.build(session, pid)
    protocols = {i.get("protocol") for i in ctx["interfaces"] if i.get("protocol")}
    assert "isoSPI" in protocols
    assert "CAN" in protocols
    # "CAN" inside "Cell" / "monitor" must NOT false-match (whole-token scan)
    comps = {i["text"] for i in ctx["interfaces"] if i.get("kind") == "component"}
    assert {"AFE", "Comms"} <= comps


# ------------------------------------------------------------------ engine: acceptance criteria
def test_acceptance_from_next_actions_and_measurable_requirements(session):
    pid = "proj-ec-ac"
    store_item(session, pid, "requirement", "State-of-charge estimate accuracy must be within 3%")
    store_item(session, pid, "requirement", "The system is nice")  # not measurable → excluded
    decision_store.save_new(
        session, id="DEC-AC", project_id=pid,
        decision=_decision("SoC", "Recommend coulomb counting",
                           next_actions=["Validate SoC accuracy on the bench"]),
    )
    decision_store.accept(session, "DEC-AC")
    session.commit()

    ctx = execution_context.build(session, pid)
    texts = [a["text"] for a in ctx["acceptance_criteria"]]
    assert any("Validate SoC accuracy on the bench" in t for t in texts)
    assert any("within 3%" in t for t in texts)
    assert not any(t == "The system is nice" for t in texts)


# ------------------------------------------------------------------ engine: standards
def test_standards_keyword_scan(session):
    pid = "proj-ec-std"
    store_item(session, pid, "requirement", "Must meet ISO 26262 ASIL-C and UN 38.3; enclosure is IP67")
    session.commit()
    ctx = execution_context.build(session, pid)
    labels = {s["text"] for s in ctx["standards"]}
    assert "ISO 26262" in labels
    assert "UN 38.3" in labels
    assert "IP67" in labels


# ------------------------------------------------------------------ engine: open risks
def test_open_risks_from_assumptions_contradictions_and_freeze_blockers(session):
    pid = "proj-ec-risk"
    assumptions_engine.create(session, pid, "Cell spread stays under 40mV")  # created → open
    challenged = assumptions_engine.create(session, pid, "Ambient never exceeds 45C")
    assumptions_engine.set_status(session, aid=challenged.id, status="challenged", project_id=pid)
    validated = assumptions_engine.create(session, pid, "Supplier lead time under 8 weeks")
    assumptions_engine.set_status(session, aid=validated.id, status="validated", project_id=pid)

    decision_store.save_new(session, id="DEC-A", project_id=pid,
                            decision=_decision("Forced-air cooling", "fan",
                                               freeze_blockers=["Thermal test not run"]))
    decision_store.accept(session, "DEC-A")
    decision_store.save_new(session, id="DEC-B", project_id=pid,
                            decision=_decision("IP67 sealed enclosure", "seal"))
    add_edge(session, source_id="DEC-A", target_id="DEC-B", relation=RelationType.conflicts_with)
    session.commit()

    ctx = execution_context.build(session, pid)
    kinds = [r["kind"] for r in ctx["open_risks"]]
    texts = [r["text"] for r in ctx["open_risks"]]
    assert kinds.count("assumption") == 2  # created + challenged, NOT the validated one
    assert any("Cell spread stays under 40mV" in t for t in texts)
    assert any("Ambient never exceeds 45C" in t for t in texts)
    assert not any("Supplier lead time" in t for t in texts)
    assert "contradiction" in kinds
    assert any("Forced-air cooling" in t for t in texts)  # contradiction names both sides
    assert "freeze_blocker" in kinds
    assert any("Thermal test not run" in t for t in texts)


# ------------------------------------------------------------------ engine: empty project
def test_empty_project_returns_empty_lists(session):
    pid = "proj-ec-empty"
    ctx = execution_context.build(session, pid)
    for key in ("accepted_decisions", "constraints", "interfaces", "acceptance_criteria",
                "standards", "open_risks"):
        assert ctx[key] == []
    assert ctx["meta"]["project_id"] == pid


# ------------------------------------------------------------------ text form
def test_text_form_has_all_section_headers(session):
    pid = "proj-ec-text"
    decision_store.save_new(session, id="DEC-T", project_id=pid,
                            decision=_decision("Topology", "Recommend isoSPI"), detail=_DETAIL)
    decision_store.accept(session, "DEC-T")
    session.commit()
    text = execution_context.to_text(execution_context.build(session, pid))
    assert "EDOS decides. Agents execute." in text
    for header in ("ACCEPTED DECISIONS", "CONSTRAINTS", "INTERFACES", "ACCEPTANCE CRITERIA",
                   "STANDARDS & OPEN RISKS"):
        assert header in text
    assert "[DEC-T]" in text


def test_generated_at_is_injected_not_wall_clock(session):
    pid = "proj-ec-ts"
    fixed = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    ctx = execution_context.build(session, pid, now=fixed)
    assert ctx["meta"]["generated_at"] == fixed.isoformat()
    # default (no now) is deterministic — no wall-clock leak
    assert execution_context.build(session, pid)["meta"]["generated_at"] is None


# ------------------------------------------------------------------ REST surface
def test_endpoint_json_and_text(client, session):
    pid = "proj-ec-api"
    store.create_project(session, id=pid, name="EC API")
    decision_store.save_new(session, id="DEC-API", project_id=pid,
                            decision=_decision("Topology", "Recommend isoSPI daisy-chain"), detail=_DETAIL)
    decision_store.accept(session, "DEC-API")
    session.commit()

    r = client.get(f"/v1/projects/{pid}/execution-context")
    assert r.status_code == 200
    body = r.json()
    assert {"accepted_decisions", "constraints", "interfaces", "acceptance_criteria",
            "standards", "open_risks", "meta"} <= set(body)
    assert body["accepted_decisions"][0]["id"] == "DEC-API"
    assert body["meta"]["generated_at"]  # endpoint injects a real timestamp

    r_txt = client.get(f"/v1/projects/{pid}/execution-context.txt")
    assert r_txt.status_code == 200
    assert "text/plain" in r_txt.headers["content-type"]
    assert "EDOS EXECUTION CONTEXT" in r_txt.text
    assert "ACCEPTED DECISIONS" in r_txt.text

    r_fmt = client.get(f"/v1/projects/{pid}/execution-context?format=text")
    assert r_fmt.status_code == 200
    assert "text/plain" in r_fmt.headers["content-type"]


def test_endpoint_404_for_unknown_project(client):
    assert client.get("/v1/projects/nope/execution-context").status_code == 404
    assert client.get("/v1/projects/nope/execution-context.txt").status_code == 404


# ------------------------------------------------------------------ helpers
_ITEM_SEQ = [0]


def store_item(session, project_id, item_type, content, domain=None):
    from edos.engines import ingestion
    _ITEM_SEQ[0] += 1
    return ingestion.ingest_item(session, id=f"IT-{_ITEM_SEQ[0]}", project_id=project_id,
                                 item_type=item_type, content=content, domain=domain)

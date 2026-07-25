"""UI-CP-10 — Timeline / Replay + Certification Matrix + Research Workspace.

Engine-level tests over a real session plus REST-surface tests via TestClient. Everything is deterministic
(no LLM); DB tests SKIP when Postgres is unreachable (see conftest).
"""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import assumptions as assumptions_engine
from edos.engines import (
    cert_matrix,
    decision_store,
    feedback,
    ingestion,
    sources,
    timeline,
)
from edos.models.decision import Decision
from edos.store import projects as store

_ITEM_SEQ = [0]


def _item(session, project_id, item_type, content, domain=None):
    _ITEM_SEQ[0] += 1
    return ingestion.ingest_item(session, id=f"IT-{_ITEM_SEQ[0]}", project_id=project_id,
                                 item_type=item_type, content=content, domain=domain)


def _decision(summary, rec, *, assumptions=None, evidence=None, confidence=0.7):
    return Decision(
        summary=summary, recommendation=rec, confidence=confidence, status="recommended",
        assumptions=assumptions or [],
        evidence=evidence or [{"claim": "grounded", "source": "REQ-1", "kind": "fact"}],
    )


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ============================================================ Timeline
def test_timeline_orders_events_and_covers_all_kinds(session):
    pid = "tl-1"
    _item(session, pid, "requirement", "Pack shall meet ISO 26262 ASIL-C", domain="Certification")
    decision_store.save_new(session, id="DEC-1", project_id=pid,
                            decision=_decision("BMS topology", "isoSPI daisy-chain",
                                               assumptions=[{"statement": "Cell spread < 40mV",
                                                             "confidence": 0.6}]))
    assumptions_engine.create(session, pid, "Ambient never exceeds 45C")
    feedback.record_outcome(session, decision_id="DEC-1", outcome="accepted")
    session.commit()

    tl = timeline.build(session, pid)
    kinds = {e["kind"] for e in tl["events"]}
    assert "decision" in kinds
    assert "assumption" in kinds
    assert "context" in kinds
    assert "outcome" in kinds
    # ordered by time (non-decreasing ISO timestamps)
    whens = [e["when"] for e in tl["events"]]
    assert whens == sorted(whens)
    # every event carries an honest coverage snapshot
    assert all("coverage" in e for e in tl["events"])
    assert tl["events"][-1]["coverage"] == tl["coverage_now"]


def test_timeline_coverage_is_monotone_and_honest(session):
    pid = "tl-2"
    # first a decision (does not raise coverage), then a domain doc + answer (do)
    decision_store.save_new(session, id="DEC-X", project_id=pid,
                            decision=_decision("Thermal", "forced-air"))
    session.commit()
    _item(session, pid, "document", "Cell datasheet rev B", domain="Hardware")
    session.commit()

    tl = timeline.build(session, pid)
    covs = [e["coverage"] for e in tl["events"]]
    assert covs == sorted(covs)  # monotone non-decreasing
    # earliest (decision) snapshot <= latest (after the doc was added)
    assert covs[0] <= covs[-1]
    assert tl["coverage_now"] == covs[-1]


def test_timeline_assumption_status_change_event(session):
    pid = "tl-3"
    a = assumptions_engine.create(session, pid, "Supplier lead time under 8 weeks")
    session.commit()
    assumptions_engine.set_status(session, aid=a.id, status="challenged", project_id=pid)
    session.commit()
    tl = timeline.build(session, pid)
    kinds = [e["kind"] for e in tl["events"]]
    assert "assumption" in kinds
    assert "assumption_status" in kinds
    status_ev = next(e for e in tl["events"] if e["kind"] == "assumption_status")
    assert "challenged" in status_ev["label"]


def test_timeline_empty_project(session):
    tl = timeline.build(session, "tl-empty")
    assert tl["events"] == []
    assert tl["coverage_now"] == 0


# ============================================================ Cert Matrix
def test_cert_matrix_regions_per_standard(session):
    pid = "cm-1"
    _item(session, pid, "requirement",
          "Design must satisfy ISO 26262 ASIL-C, AIS 156 for India, and ECE R100 for Europe. "
          "Also UN 38.3 for transport.")
    session.commit()
    m = cert_matrix.build(session, pid)
    assert m["regions"] == ["India", "Europe"]
    by = {s["standard"]: s for s in m["standards"]}
    assert set(by["ISO 26262"]["regions"]) == {"India", "Europe"}
    assert by["AIS 156"]["regions"] == ["India"]
    assert by["ECE R100"]["regions"] == ["Europe"]
    assert set(by["UN 38.3"]["regions"]) == {"India", "Europe"}


def test_cert_matrix_cost_timeline_only_when_present(session):
    pid = "cm-2"
    # ISO 26262 co-mentioned with a cost + timeline; AIS 156 with neither
    _item(session, pid, "requirement",
          "ISO 26262 assessment is estimated at $45,000 and takes 12 weeks.")
    _item(session, pid, "requirement", "AIS 156 approval is required for the India launch.")
    session.commit()
    by = {s["standard"]: s for s in cert_matrix.build(session, pid)["standards"]}
    assert by["ISO 26262"].get("cost") == "$45,000"  # trailing punctuation trimmed
    assert by["ISO 26262"].get("timeline") == "12 weeks"
    # nothing fabricated for AIS 156
    assert "cost" not in by["AIS 156"]
    assert "timeline" not in by["AIS 156"]


def test_cert_matrix_empty_when_no_standards(session):
    pid = "cm-3"
    _item(session, pid, "requirement", "Build a nice enclosure with rounded corners.")
    session.commit()
    m = cert_matrix.build(session, pid)
    assert m["standards"] == []
    assert m["regions"] == ["India", "Europe"]


# ============================================================ Research Workspace / sources
def test_sources_for_decision(session):
    pid = "src-1"
    _item(session, pid, "document", "MAX17853 BMS AFE datasheet", domain="Hardware")
    _item(session, pid, "requirement", "not a document")  # excluded
    decision_store.save_new(
        session, id="DEC-S", project_id=pid,
        decision=_decision("Comms", "isoSPI",
                           evidence=[{"claim": "isoSPI is robust", "source": "MAX17853 datasheet",
                                      "kind": "external"},
                                     {"claim": "CAN host bus", "source": "REQ-2", "kind": "fact"}]),
    )
    session.commit()
    res = sources.for_decision(session, "DEC-S")
    assert res["decision_id"] == "DEC-S"
    assert res["project_id"] == pid
    docs = [d["content"] for d in res["documents"]]
    assert "MAX17853 BMS AFE datasheet" in docs
    assert "not a document" not in docs
    ev_sources = {e["source"] for e in res["evidence"]}
    assert "MAX17853 datasheet" in ev_sources
    assert "REQ-2" in ev_sources


def test_sources_for_decision_404_when_missing(session):
    assert sources.for_decision(session, "nope") is None


def test_sources_for_project_unions_evidence(session):
    pid = "src-2"
    _item(session, pid, "document", "datasheet A", domain="Firmware")
    decision_store.save_new(session, id="D1", project_id=pid,
                            decision=_decision("a", "b",
                                               evidence=[{"claim": "c1", "source": "S1"}]))
    decision_store.save_new(session, id="D2", project_id=pid,
                            decision=_decision("d", "e",
                                               evidence=[{"claim": "c2", "source": "S2"}]))
    session.commit()
    res = sources.for_project(session, pid)
    assert len(res["documents"]) == 1
    ev_sources = {e["source"] for e in res["evidence"]}
    assert {"S1", "S2"} <= ev_sources
    assert all("decision_id" in e for e in res["evidence"])


# ============================================================ REST surface
def test_rest_endpoints(client, session):
    pid = "cp10-api"
    store.create_project(session, id=pid, name="CP10 API")
    _item(session, pid, "document", "Battery cell datasheet — ISO 26262 relevant", domain="Certification")
    decision_store.save_new(session, id="DEC-API", project_id=pid,
                            decision=_decision("BMS", "isoSPI daisy-chain (ISO 26262, AIS 156)"))
    feedback.record_outcome(session, decision_id="DEC-API", outcome="accepted")
    session.commit()

    r_tl = client.get(f"/v1/projects/{pid}/timeline")
    assert r_tl.status_code == 200
    assert r_tl.json()["events"]

    r_cm = client.get(f"/v1/projects/{pid}/cert-matrix")
    assert r_cm.status_code == 200
    labels = {s["standard"] for s in r_cm.json()["standards"]}
    assert "ISO 26262" in labels and "AIS 156" in labels

    r_ds = client.get("/v1/decisions/DEC-API/sources")
    assert r_ds.status_code == 200
    assert r_ds.json()["documents"]

    r_ps = client.get(f"/v1/projects/{pid}/sources")
    assert r_ps.status_code == 200

    # 404s
    assert client.get("/v1/projects/nope/timeline").status_code == 404
    assert client.get("/v1/projects/nope/cert-matrix").status_code == 404
    assert client.get("/v1/projects/nope/sources").status_code == 404
    assert client.get("/v1/decisions/nope/sources").status_code == 404

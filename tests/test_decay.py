"""UI-CP-8 — Assumption Decay Alert (background re-check).

Engine-level tests (``engines.decay``) over a real session plus REST-surface tests via TestClient. Aging is
made deterministic by **back-dating ``created_at`` and injecting ``now``** — never the real wall-clock (per
CLAUDE.md / the ticket). DB tests SKIP when Postgres is unreachable (see conftest), so the gate stays green
without infra.
"""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import assumptions as assumptions_engine
from edos.engines import decay, decision_store
from edos.engines.graph_builder import add_edge
from edos.models.decision import Decision
from edos.models.entities import RelationType

UTC = dt.UTC


def _decision(summary, rec, *, assumptions=None):
    return Decision(
        summary=summary, recommendation=rec, confidence=0.7, status="recommended",
        assumptions=assumptions or [],
        evidence=[{"claim": "grounded", "source": "REQ-1", "kind": "fact"}],
    )


def _backdate(session, row, *, days):
    """Push an assumption's created_at into the past so the age window can be tested deterministically."""
    row.created_at = dt.datetime.now(UTC) - dt.timedelta(days=days)
    session.flush()


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------------ engine: aged assumptions
def test_aged_unvalidated_assumption_triggers(session):
    pid = "proj-age"
    a = assumptions_engine.create(session, pid, "Cell spread stays under 40mV")
    _backdate(session, a, days=45)
    session.commit()

    now = dt.datetime.now(UTC)
    alerts = decay.decay_scan(session, pid, now=now, age_days=30)
    aged = [x for x in alerts if x.type == "assumption_decay"]
    assert len(aged) == 1
    assert aged[0].subject == a.id
    assert "needs re-validation" in aged[0].message
    assert "age 45 days" in aged[0].message
    assert aged[0].severity == "medium"


def test_young_assumption_does_not_trigger(session):
    pid = "proj-young"
    a = assumptions_engine.create(session, pid, "Ambient stays below 40C")
    _backdate(session, a, days=5)  # inside the 30-day window
    session.commit()
    alerts = decay.decay_scan(session, pid, now=dt.datetime.now(UTC), age_days=30)
    assert [x for x in alerts if x.type == "assumption_decay"] == []


def test_validated_assumption_does_not_decay(session):
    pid = "proj-val"
    a = assumptions_engine.create(session, pid, "Supplier lead time under 8 weeks")
    _backdate(session, a, days=90)
    assumptions_engine.set_status(session, aid=a.id, status="validated", project_id=pid)
    session.commit()
    # old but already given a verdict → not re-flagged for age
    alerts = decay.decay_scan(session, pid, now=dt.datetime.now(UTC), age_days=30)
    assert [x for x in alerts if x.type == "assumption_decay"] == []


def test_now_is_injectable_not_wall_clock(session):
    """The exact same row is under-threshold for one injected `now` and over-threshold for a later one."""
    pid = "proj-inj"
    a = assumptions_engine.create(session, pid, "Firmware OTA fits in 512KB")
    base = dt.datetime(2026, 1, 1, tzinfo=UTC)
    a.created_at = base
    session.commit()

    # 10 days later → within window, no alert
    early = decay.decay_scan(session, pid, now=base + dt.timedelta(days=10), age_days=30)
    assert [x for x in early if x.type == "assumption_decay"] == []
    # 40 days later → aged, alert fires
    late = decay.decay_scan(session, pid, now=base + dt.timedelta(days=40), age_days=30)
    aged = [x for x in late if x.type == "assumption_decay"]
    assert len(aged) == 1 and "age 40 days" in aged[0].message


# ------------------------------------------------------------------ engine: cross-decision contradiction
def test_cross_decision_contradiction_caught(session):
    pid = "proj-x"
    decision_store.save_new(session, id="DEC-A", project_id=pid,
                            decision=_decision("Forced-air cooling", "fan"))
    decision_store.save_new(session, id="DEC-B", project_id=pid,
                            decision=_decision("IP67 sealed enclosure", "seal"))
    add_edge(session, source_id="DEC-A", target_id="DEC-B", relation=RelationType.conflicts_with)
    session.commit()

    alerts = decay.decay_scan(session, pid, now=dt.datetime.now(UTC))
    xs = [x for x in alerts if x.type == "cross_decision_contradiction"]
    assert len(xs) == 1
    assert xs[0].severity == "high"  # no assumption participates
    assert "Forced-air cooling" in xs[0].message and "IP67 sealed enclosure" in xs[0].message


def test_contradiction_with_participating_assumption_is_critical(session):
    """The PDF's marquee moment: an assumption grounded in a decision that now conflicts elsewhere."""
    pid = "proj-a12"
    d1 = decision_store.save_new(
        session, id="DEC-A", project_id=pid,
        decision=_decision("Forced-air cooling", "fan",
                           assumptions=[{"statement": "Forced-air cooling is sufficient", "confidence": 0.6,
                                         "risk_if_wrong": "Overheats when sealed"}]),
    )
    decision_store.save_new(session, id="DEC-B", project_id=pid,
                            decision=_decision("IP67 sealed enclosure", "seal"))
    # mirror the inline assumption → first-class A1 sourced from DEC-A
    assumptions_engine.upsert_from_decision(session, pid, decision_store.to_decision(d1), d1.id)
    add_edge(session, source_id="DEC-A", target_id="DEC-B", relation=RelationType.conflicts_with)
    session.commit()

    alerts = decay.decay_scan(session, pid, now=dt.datetime.now(UTC))
    xs = [x for x in alerts if x.type == "cross_decision_contradiction"]
    assert len(xs) == 1
    assert xs[0].severity == "critical"
    assert "A1" in xs[0].message  # the participating assumption is named


def test_no_conflict_no_contradiction_alert(session):
    pid = "proj-clean"
    decision_store.save_new(session, id="DEC-A", project_id=pid, decision=_decision("A", "a"))
    decision_store.save_new(session, id="DEC-B", project_id=pid, decision=_decision("B", "b"))
    session.commit()
    alerts = decay.decay_scan(session, pid, now=dt.datetime.now(UTC))
    assert [x for x in alerts if x.type == "cross_decision_contradiction"] == []


# ------------------------------------------------------------------ notify hook is inert in tests
def test_notify_is_noop_in_tests(session):
    # PYTEST_CURRENT_TEST is set during the suite → the ntfy push must never fire.
    from edos.engines.watchdog import Alert
    crit = [Alert("cross_decision_contradiction", "X", "boom", "critical")]
    assert decay.notify_critical_contradiction(crit) is False
    assert decay.notify_critical_contradiction(crit, enabled=True) is False


# ------------------------------------------------------------------ REST surface
def test_decay_alerts_endpoint(session, client):
    # `client` overrides get_session to yield this same `session`, so we build the decision web via the
    # engines and exercise the HTTP surface for the read.
    pid = client.post("/v1/projects", json={"name": "Decay P"}).json()["id"]
    d1 = decision_store.save_new(
        session, id="DEC-A", project_id=pid,
        decision=_decision("Forced-air cooling", "fan",
                           assumptions=[{"statement": "Forced-air cooling is sufficient", "confidence": 0.6,
                                         "risk_if_wrong": "Overheats when sealed"}]),
    )
    decision_store.save_new(session, id="DEC-B", project_id=pid,
                            decision=_decision("IP67 sealed enclosure", "seal"))
    assumptions_engine.upsert_from_decision(session, pid, decision_store.to_decision(d1), d1.id)
    add_edge(session, source_id="DEC-A", target_id="DEC-B", relation=RelationType.conflicts_with)
    session.commit()

    # inject `now` 40 days ahead via as_of → the fresh assumption is now "aged"
    future = (dt.datetime.now(UTC) + dt.timedelta(days=40)).isoformat()
    alerts = client.get(f"/v1/projects/{pid}/decay-alerts",
                        params={"age_days": 30, "as_of": future}).json()
    types = {a["type"] for a in alerts}
    assert "assumption_decay" in types
    assert "cross_decision_contradiction" in types
    xa = next(a for a in alerts if a["type"] == "cross_decision_contradiction")
    assert xa["severity"] == "critical"  # A1 sourced from the conflicting decision participates

    # existing /alerts endpoint still works unchanged
    assert client.get(f"/v1/projects/{pid}/alerts").status_code == 200
    # unknown project → 404; bad as_of → 422
    assert client.get("/v1/projects/nope/decay-alerts").status_code == 404
    assert client.get(f"/v1/projects/{pid}/decay-alerts", params={"as_of": "not-a-date"}).status_code == 422

"""CP-11 — decision persistence: immutable, versioned, history, accept flow."""
from edos.engines import decision_store as ds
from edos.models.decision import Decision

BASE = dict(
    summary="Host MCU = ESP32-C6",
    recommendation="Use ESP32-C6 for sub-$12 BOM",
    confidence=0.82,
    status="recommended",
    evidence=[{"claim": "cheap + BLE", "source": "REQ-5", "kind": "fact"}],
)


def _decision(**over):
    return Decision(**{**BASE, **over})


def test_save_and_get_latest(session):
    row = ds.save_new(session, id="D-1", project_id="p1", decision=_decision())
    assert row.version == 1
    got = ds.get_latest(session, "D-1")
    assert got.title == "Host MCU = ESP32-C6"
    assert ds.to_decision(got).confidence == 0.82  # round-trips full contract


def test_accept_appends_version_and_leaves_prior_immutable(session):
    ds.save_new(session, id="D-1", project_id="p1", decision=_decision())
    accepted = ds.accept(session, "D-1")
    session.commit()

    hist = ds.history(session, "D-1")
    assert [r.version for r in hist] == [1, 2]
    assert hist[0].status == "recommended"      # v1 untouched
    assert hist[1].status == "accepted"         # v2 accepted
    assert accepted.parent_version == 1


def test_accept_with_edits_creates_revised_version(session):
    ds.save_new(session, id="D-1", project_id="p1", decision=_decision())
    ds.accept(session, "D-1", edited=_decision(confidence=0.9, recommendation="Use ESP32-C6 (price confirmed)"))
    session.commit()
    latest = ds.get_latest(session, "D-1")
    assert latest.version == 2
    assert latest.status == "accepted"
    assert latest.confidence == 0.9
    assert ds.to_decision(latest).recommendation == "Use ESP32-C6 (price confirmed)"


def test_list_for_project_returns_latest_per_decision(session):
    ds.save_new(session, id="D-1", project_id="p1", decision=_decision())
    ds.accept(session, "D-1")  # D-1 now at v2
    ds.save_new(session, id="D-2", project_id="p1", decision=_decision(summary="ADC approach"))
    ds.save_new(session, id="D-9", project_id="other", decision=_decision())
    session.commit()

    latest = {r.id: r.version for r in ds.list_for_project(session, "p1")}
    assert latest == {"D-1": 2, "D-2": 1}  # only p1, latest versions


def test_accept_missing_decision_returns_none(session):
    assert ds.accept(session, "nope") is None

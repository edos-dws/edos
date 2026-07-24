"""CP-15 — interactive resolution: assumption + conflict resolution."""
from edos.engines import decision_store, ingestion, resolution
from edos.models.decision import Decision


def _persist(session, did="D-1"):
    d = Decision(
        summary="Use ESP32-C6", recommendation="Adopt ESP32-C6", confidence=0.7, status="recommended",
        evidence=[{"claim": "cheap", "source": "REQ-5", "kind": "fact"}],
        freeze_blockers=["Unconfirmed: assumption about ADC accuracy must be validated on bench"],
    )
    return decision_store.save_new(session, id=did, project_id="p1", decision=d)


def test_resolve_assumption_appends_version_and_clears_blocker(session):
    _persist(session)
    row = resolution.resolve_assumption(
        session, decision_id="D-1", statement="assumption about ADC accuracy",
        resolution="Measured 12-bit ADC meets +/-0.1 with oversampling", resolved_by="eng-1",
    )
    session.commit()
    assert row.version == 2
    decision = decision_store.to_decision(row)
    assert decision.freeze_blockers == []                       # blocker cleared
    assert len(resolution.resolutions_for(session, "D-1")) == 1  # recorded


def test_resolve_missing_decision_returns_none(session):
    assert resolution.resolve_assumption(
        session, decision_id="nope", statement="x", resolution="y") is None


def test_resolve_conflict_closes_edges_and_restores_validity(session):
    ingestion.ingest_item(session, id="DEC-1", project_id="p1", item_type="decision", content="use ESP32")
    ingestion.ingest_item(session, id="DEC-2", project_id="p1", item_type="decision",
                          content="this conflicts with DEC-1, use nRF52")
    from edos.db.models import ProjectItem
    assert session.get(ProjectItem, "DEC-1").validity == "conflicted"

    closed = resolution.resolve_conflict(session, node_a="DEC-1", node_b="DEC-2")
    assert closed >= 1
    assert session.get(ProjectItem, "DEC-1").validity == "active"   # restored

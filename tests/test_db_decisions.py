"""Ticket 2.1 — decisions are immutable + versioned."""
from sqlalchemy import select

from edos.db.models import DecisionRecord, new_decision_version


def test_new_version_leaves_original_unchanged(session):
    v1 = DecisionRecord(
        id="D-1", project_id="p1", title="MCU=nRF52840", rationale="single chip", confidence=0.6,
        status="recommended", version=1,
    )
    session.add(v1)
    session.flush()

    new_decision_version(session, v1, title="MCU=STM32WL", confidence=0.88, status="verified")
    session.commit()

    rows = session.scalars(
        select(DecisionRecord).where(DecisionRecord.id == "D-1").order_by(DecisionRecord.version)
    ).all()
    assert [r.version for r in rows] == [1, 2]

    original = rows[0]
    assert original.title == "MCU=nRF52840"       # untouched
    assert original.confidence == 0.6
    assert original.status == "recommended"
    assert original.parent_version is None

    latest = rows[1]
    assert latest.title == "MCU=STM32WL"
    assert latest.confidence == 0.88
    assert latest.status == "verified"
    assert latest.parent_version == 1

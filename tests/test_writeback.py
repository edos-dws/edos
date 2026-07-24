"""CP-15 — write-back: an accepted decision folds knowledge into the project graph + embeddings."""
from sqlalchemy import func, select

from edos.db.models import DocumentChunk, ProjectItem
from edos.engines import writeback
from edos.models.decision import Decision

DEC = Decision(
    summary="Use ESP32-C6", recommendation="Adopt ESP32-C6 host MCU for sub-$12 BOM",
    confidence=0.85, status="recommended",
    evidence=[{"claim": "ESP32-C6 has BLE 5.3", "source": "datasheet", "kind": "fact"}],
)


def test_accepted_decision_creates_knowledge_nodes(session):
    created = writeback.process_accepted(session, decision_id="DEC-1", project_id="p1", decision=DEC)
    assert created  # at least the recommendation knowledge item
    items = session.scalars(select(ProjectItem).where(ProjectItem.project_id == "p1")).all()
    assert len(items) == len(created)
    # each knowledge node is embedded for retrieval
    n_chunks = session.scalar(select(func.count()).select_from(DocumentChunk))
    assert n_chunks == len(created)

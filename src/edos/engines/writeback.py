"""Write-back (CP-15, roadmap Ch6 §11) — an accepted decision updates project knowledge.

On accept, the passive pipeline fans `DecisionAccepted` out to jobs; here we run them synchronously
(a real broker plugs in behind the same interface later): extract knowledge from the decision and fold it
back into the project as graph nodes + embeddings, so future retrieval sees it.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from edos.engines import ingestion
from edos.engines.knowledge import KnowledgeEngine
from edos.models.decision import Decision
from edos.pipeline.passive import InMemoryJobQueue, emit


def process_accepted(session: Session, *, decision_id: str, project_id: str, decision: Decision) -> list[str]:
    """Extract knowledge from an accepted decision and ingest it (embed + graph). Returns new node ids."""
    emit("DecisionAccepted", {"decision_id": decision_id, "project_id": project_id}, InMemoryJobQueue())
    knowledge = KnowledgeEngine().process(decision, project_id)
    created: list[str] = []
    for i, item in enumerate(knowledge):
        node_id = f"{decision_id}-kn-{i}"
        content = f"[from {decision_id}] {item.content}"
        ingestion.ingest_item(session, id=node_id, project_id=project_id, item_type="document",
                              content=content)
        created.append(node_id)
    return created

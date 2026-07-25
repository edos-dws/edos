"""Ingestion engine (CP-12) — turn a project item into a connected, embedded, valid graph node.

Pipeline per item: persist node → embed content (→ DocumentChunk) → extract explicit-reference edges →
apply integrity + temporal side-effects → flag `needs_linking` if it entered with no relation (soft, never
a silent orphan). Semantic/implicit edge + conflict detection is LLM-gated and deferred (CP-12 report).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import DecisionRecord, DocumentChunk, ProjectItem
from edos.engines import graph_builder
from edos.engines.embeddings import EmbeddingProvider, default_embedder


def _known_ids(session: Session, project_id: str, exclude: str) -> list[str]:
    item_ids = session.scalars(
        select(ProjectItem.id).where(
            ProjectItem.project_id == project_id, ProjectItem.id != exclude
        )
    ).all()
    decision_ids = session.scalars(
        select(DecisionRecord.id).where(DecisionRecord.project_id == project_id).distinct()
    ).all()
    return list(dict.fromkeys([*item_ids, *decision_ids]))  # unique, order-preserving


def ingest_item(
    session: Session, *, id: str, project_id: str, item_type: str, content: str,
    domain: str | None = None, embedder: EmbeddingProvider | None = None,
) -> ProjectItem:
    embedder = embedder or default_embedder()

    item = ProjectItem(id=id, project_id=project_id, item_type=item_type, content=content,
                       validity="active", domain=domain)
    session.add(item)
    session.flush()

    # embed for semantic retrieval (CP-13)
    session.add(DocumentChunk(project_id=project_id, document_id=id, content=content,
                              embedding=embedder.embed(content)))

    # explicit-reference edges → integrity + temporal side-effects
    edges = graph_builder.extract_edges(content, _known_ids(session, project_id, exclude=id))
    added = 0
    for target_id, relation in edges:
        try:
            graph_builder.add_edge(session, source_id=id, target_id=target_id, relation=relation)
            added += 1
        except graph_builder.GraphIntegrityError:
            continue  # skip an edge that would violate an invariant; item still ingests

    if added == 0:
        item.needs_linking = True  # soft flag — surfaced for linking, never a silent orphan
    session.flush()
    return item

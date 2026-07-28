"""Ingestion engine (CP-12) — turn a project item into a connected, embedded, valid graph node.

Pipeline per item: persist node → embed content (→ DocumentChunk) → extract explicit-reference edges →
apply integrity + temporal side-effects → flag `needs_linking` if it entered with no relation (soft, never
a silent orphan). Semantic/implicit edge + conflict detection is LLM-gated and deferred (CP-12 report).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.graph import RelationType
from edos.db.models import DecisionRecord, DocumentChunk, ProjectItem
from edos.engines import extraction, graph_builder
from edos.engines.embeddings import EmbeddingProvider, default_embedder


def _is_rich(content: str) -> bool:
    """Only worth extracting facts from something with buried detail — a long paragraph / datasheet blurb,
    not an already-atomic one-liner like 'peak 200A'."""
    return len((content or "").strip()) >= 120


def _extract_facts(session: Session, *, source_id: str, project_id: str, content: str,
                   domain: str | None, embedder: EmbeddingProvider) -> int:
    """Pull the atomic facts out of a rich item and store each as its own retrievable item (embedded, and
    linked `derived_from` the source for provenance). Clean discrete facts retrieve far better than a noisy
    paragraph, and give the model exact, citable inputs. No recursion (children ingest with extraction off)."""
    src_norm = " ".join((content or "").lower().split())
    added = 0
    for fact in extraction.extract(content)[:12]:
        fc = (fact.get("content") or "").strip()
        if len(fc) < 10 or " ".join(fc.lower().split()) == src_norm:
            continue  # skip empties and the "extracted the whole sentence" case
        fid = "fact-" + uuid.uuid4().hex[:10]
        child = ingest_item(session, id=fid, project_id=project_id, item_type=fact["type"],
                            content=fc, domain=domain, embedder=embedder, extract_facts=False)
        try:
            graph_builder.add_edge(session, source_id=fid, target_id=source_id,
                                   relation=RelationType.derived_from)
            child.needs_linking = False  # it IS linked (to its source), don't flag it as an orphan
        except graph_builder.GraphIntegrityError:
            pass
        added += 1
    session.flush()
    return added


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
    extract_facts: bool = False,
) -> ProjectItem:
    embedder = embedder or default_embedder()

    item = ProjectItem(id=id, project_id=project_id, item_type=item_type, content=content,
                       validity="active", domain=domain)
    session.add(item)
    session.flush()

    # Embed for semantic retrieval (CP-13) — BEST-EFFORT. A provider outage (e.g. a 429 quota exhaustion on
    # the embedding API) must NEVER 500 the ingest and lose the engineer's item: the embedding is an
    # enhancement, the item is the data. On failure we persist the item WITHOUT a chunk (retrieval degrades to
    # its other signals for this item until it is re-embedded) rather than rolling the whole ingest back.
    try:
        vector = embedder.embed(content)  # the provider call — the part that can 429/quota-fail
        session.add(DocumentChunk(project_id=project_id, document_id=id, content=content, embedding=vector,
                                  embedding_model=embedder.name, embedding_dim=embedder.dim))  # A4 provenance
        session.flush()
    except Exception:  # noqa: BLE001, S110 — embedding is best-effort; a provider/quota error must not lose the item
        pass  # keep the already-flushed item; skip only its semantic chunk (re-embed later)

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

    # A5 semantic edges (Layer 2, flag-gated): classify this item against its semantic neighbours and add
    # low-stakes edges (high-stakes conflict/supersede are surfaced, not auto-applied). BEST-EFFORT — a
    # provider/quota outage or any failure must never fail the ingest; offline it is a no-op.
    from edos.config import settings
    if settings.semantic_edges:
        try:
            from edos.engines import graph_semantic
            graph_semantic.propose_semantic_edges(session, project_id=project_id, item_id=id)
        except Exception:  # noqa: BLE001, S110 — semantic edges are additive; never block the ingest
            pass

    # #5 structured fact extraction — turn a rich item into clean, discrete, retrievable facts. BEST-EFFORT:
    # it calls the extraction LLM and embeds each fact, so a provider/quota outage must not fail the ingest —
    # the source item is already safely persisted; the derived facts are an enhancement we can rebuild later.
    if extract_facts and _is_rich(content):
        try:
            _extract_facts(session, source_id=id, project_id=project_id, content=content,
                           domain=domain, embedder=embedder)
        except Exception:  # noqa: BLE001, S110 — fact extraction is additive; never fail the ingest on it
            pass
    return item

"""Ticket 2.3 — pgvector document chunks + nearest-k retrieval."""
from sqlalchemy import select

from edos.db.models import EMBED_DIM, DocumentChunk


def _vec(*first):
    """Build an EMBED_DIM vector padded with zeros."""
    v = list(first) + [0.0] * (EMBED_DIM - len(first))
    return v[:EMBED_DIM]


def nearest_chunks(session, query_embedding, k=5, project_id=None):
    q = select(DocumentChunk).order_by(DocumentChunk.embedding.l2_distance(query_embedding)).limit(k)
    if project_id is not None:
        q = q.where(DocumentChunk.project_id == project_id)
    return list(session.scalars(q))


def test_nearest_returns_closest_first(session):
    session.add_all([
        DocumentChunk(project_id="p1", document_id="d1", content="near",  embedding=_vec(1.0, 0.0)),
        DocumentChunk(project_id="p1", document_id="d1", content="mid",   embedding=_vec(0.0, 1.0)),
        DocumentChunk(project_id="p1", document_id="d1", content="far",   embedding=_vec(9.0, 9.0)),
    ])
    session.commit()

    results = nearest_chunks(session, _vec(1.0, 0.05), k=2, project_id="p1")
    assert len(results) == 2
    assert results[0].content == "near"       # closest by L2
    assert results[-1].content != "far"       # far one excluded from top-2

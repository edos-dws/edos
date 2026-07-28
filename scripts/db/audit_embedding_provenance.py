"""Audit stored embedding provenance (A4 §0) — detect the latent mixed-space bug.

The stub and Gemini both emit 768-dim vectors in DIFFERENT vector spaces. If a chunk was embedded offline
(stub-space) but the query now embeds with Gemini, dense cosine compares unrelated spaces → meaningless
scores, silently masked by lexical/graph. Run this against the live DB BEFORE trusting semantic retrieval:

  DATABASE_URL=... EDOS_EMBEDDER=gemini .venv/bin/python scripts/db/audit_embedding_provenance.py

It reports how many chunks are: current-embedder · a different/stale embedder · provenance-unset (NULL,
pre-A4) · no vector (NULL embedding). Anything not on the current embedder needs the backfill
(scripts/db/migrate_embeddings_768.py) before its dense retrieval is trustworthy.
"""
import os

from sqlalchemy import create_engine, func, select

from edos.db.models import DocumentChunk
from edos.engines.embeddings import get_embedder


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    embedder = get_embedder()
    with engine.connect() as c:
        total = c.execute(select(func.count()).select_from(DocumentChunk)).scalar_one()
        by_model = c.execute(
            select(DocumentChunk.embedding_model, func.count())
            .group_by(DocumentChunk.embedding_model)
        ).all()
        no_vector = c.execute(
            select(func.count()).select_from(DocumentChunk).where(DocumentChunk.embedding.is_(None))
        ).scalar_one()

    print(f"Current embedder: {embedder.name} (dim {embedder.dim})")
    print(f"document_chunks total: {total}")
    print("\nprovenance (embedding_model → count):")
    stale = 0
    for model, count in sorted(by_model, key=lambda r: (r[0] is not None, r[0] or "")):
        label = "(unset — pre-A4)" if model is None else \
                "(CURRENT ✓)" if model == embedder.name else "(STALE — different space ✗)"
        if model != embedder.name:
            stale += count
        print(f"  {model!s:24} {count:6}  {label}")
    print(f"\nchunks with NULL embedding (dense-skipped, honest): {no_vector}")
    if stale:
        print(f"\n⚠ {stale} chunk(s) are NOT on the current embedder — dense retrieval over them compares "
              f"across vector spaces. Run scripts/db/migrate_embeddings_768.py to backfill.")
    else:
        print("\n✓ Every embedded chunk is on the current embedder — no mixed-space risk.")


if __name__ == "__main__":
    main()

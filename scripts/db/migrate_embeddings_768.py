"""One-shot: migrate document_chunks.embedding from the stub dim to the real embedder dim, then re-embed.

Safe to re-run. Steps:
  1. NULL existing embeddings (old stub vectors are incompatible with the new dimension).
  2. ALTER the pgvector column to EMBED_DIM.
  3. Re-embed every chunk's content with the configured embedder (EDOS_EMBEDDER — gemini in live).

Run with the real embedder, e.g.:
  DATABASE_URL=... GEMINI_API_KEY=... EDOS_EMBEDDER=gemini .venv/bin/python scripts/db/migrate_embeddings_768.py
"""
import os

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from edos.db.models import EMBED_DIM, DocumentChunk
from edos.engines.embeddings import get_embedder


def main() -> None:
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url)
    embedder = get_embedder()
    print(f"Embedder: {embedder.name} · target dim: {EMBED_DIM}")

    # 1 + 2: reset old vectors and re-type the column (autocommit for DDL).
    with engine.connect() as c:
        c.execute(text("UPDATE document_chunks SET embedding = NULL"))
        c.commit()
        c.execute(text(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({EMBED_DIM})"))
        c.commit()
    print(f"Column altered to vector({EMBED_DIM}); old embeddings cleared.")

    # 3: re-embed every chunk.
    with Session(engine) as s:
        chunks = list(s.scalars(select(DocumentChunk)))
        n = len(chunks)
        for i, ch in enumerate(chunks, 1):
            ch.embedding = embedder.embed(ch.content or " ")
            if i % 10 == 0 or i == n:
                print(f"  re-embedded {i}/{n}")
        s.commit()
    print(f"Backfill complete: {n} chunk(s) re-embedded with '{embedder.name}'.")


if __name__ == "__main__":
    main()

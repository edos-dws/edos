"""Backfill / re-embed document_chunks with the configured embedder — SAFE, RESUMABLE, PACED (A4).

The stub and Gemini both emit 768-dim vectors but in **different vector spaces**. This backfill re-embeds
every chunk that was NOT produced by the current embedder (stub-space or provenance-unset rows) and stamps
its provenance, so:
  * a 429-interrupted run **resumes** (it only touches rows whose `embedding_model` ≠ the current embedder);
  * re-running when everything is current is a **no-op** (idempotent);
  * during a partial run, un-migrated rows keep their prior state — dense retrieval skips NULL / mismatched
    rows honestly rather than comparing across spaces.

Run with the real embedder:
  DATABASE_URL=... GEMINI_API_KEY=... EDOS_EMBEDDER=gemini .venv/bin/python scripts/db/migrate_embeddings_768.py

Env knobs: EMBED_PACE_SECONDS (default 0.0), EMBED_RETRY_DELAY (default 30s on a 429), EMBED_COMMIT_EVERY (25).

NOTE: the embed API accepts batched inputs — embedding N chunks per call would cut 429s further. That batch
path is a follow-up (needs `embed_batch` on the provider); this script paces + retries per chunk, which is
enough for the current corpus size.
"""
import os
import time

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from edos.db.models import EMBED_DIM, DocumentChunk
from edos.engines.embeddings import get_embedder

_PACE = float(os.environ.get("EMBED_PACE_SECONDS", "0.0"))
_RETRY_DELAY = float(os.environ.get("EMBED_RETRY_DELAY", "30"))
_COMMIT_EVERY = int(os.environ.get("EMBED_COMMIT_EVERY", "25"))


def _ensure_schema(engine) -> None:
    """Additive, idempotent DDL: provenance columns + the vector dim (no-op if already EMBED_DIM)."""
    with engine.connect() as c:
        c.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_model text"))
        c.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_dim integer"))
        c.execute(text(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({EMBED_DIM})"))
        c.commit()


def _embed_with_retry(embedder, content: str) -> list[float]:
    """Embed one chunk; on a 429/rate error retry once after a delay (mirrors the live runner)."""
    try:
        return embedder.embed(content or " ")
    except Exception as exc:
        msg = str(exc).lower()
        if "429" in msg or "resource_exhausted" in msg or "rate" in msg:
            print(f"    rate-limited; retrying in {_RETRY_DELAY:.0f}s …")
            time.sleep(_RETRY_DELAY)
            return embedder.embed(content or " ")
        raise


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    embedder = get_embedder()
    print(f"Embedder: {embedder.name} · dim: {embedder.dim} (target {EMBED_DIM})")

    _ensure_schema(engine)

    with Session(engine) as s:
        # Resumable: only rows NOT already produced by the current embedder (stub-space, or provenance-unset).
        stale = list(s.scalars(select(DocumentChunk).where(
            (DocumentChunk.embedding_model.is_(None)) | (DocumentChunk.embedding_model != embedder.name)
        )))
        n = len(stale)
        if n == 0:
            print("Nothing to do — every chunk is already embedded by the current embedder (idempotent).")
            return
        print(f"Re-embedding {n} stale/unset chunk(s) with '{embedder.name}' …")
        for i, ch in enumerate(stale, 1):
            ch.embedding = _embed_with_retry(embedder, ch.content)
            ch.embedding_model = embedder.name
            ch.embedding_dim = embedder.dim
            if i % _COMMIT_EVERY == 0:
                s.commit()  # checkpoint so a crash/quota-stop resumes from here, not from zero
                print(f"  …{i}/{n} (committed)")
            if _PACE:
                time.sleep(_PACE)
        s.commit()
        print(f"Backfill complete: {n} chunk(s) now provenance='{embedder.name}'.")


if __name__ == "__main__":
    main()

# CP-12 Report — Ingestion + Embeddings + Graph (+ temporal validity + conflict edges)

**Status:** ✅ Complete (with flagged deferrals) · **Branch:** `cp-12` → `develop` · **Gate:** self-merge

## What was built
The data + connected-graph layer the Retriever (CP-13) will fetch from.

- **DB:** `ProjectItem` node table (id, project_id, item_type, content, **validity**, **needs_linking**);
  `GraphEdge.validity` added. Alembic `0004`.
- **Embeddings** (`engines/embeddings.py`): `EmbeddingProvider` interface + deterministic `StubEmbeddingProvider`
  (token-hash → L2-normalized vector). Real model = OD-1 (deferred).
- **Graph builder** (`engines/graph_builder.py`): explicit-reference edge extraction (nearest-keyword relation),
  integrity (no dangling, `supersedes` DAG/cycle-reject, `conflicts_with` symmetric), temporal side-effects
  (supersedes→superseded, invalidates→stale, conflicts→conflicted both sides).
- **Ingestion** (`engines/ingestion.py`): node → embed (→DocumentChunk) → extract edges → integrity/temporal →
  `needs_linking` soft-flag when an item enters with no relation (never a silent orphan).
- **REST:** `POST /v1/projects/{pid}/items`, `GET /v1/projects/{pid}/items`.

## Tickets
- [x] 12.1 Item ingestion · [x] 12.2 Embedding provider (stub) · [x] 12.3 Chunk+embed pipeline
- [x] 12.4 Edge extraction — **explicit-reference** done; *implicit/semantic (LLM) extraction deferred* (flag).
- [x] 12.5 No-orphan guarantee (soft `needs_linking` flag)
- [x] 12.6 Graph integrity (dangling / DAG / symmetric)
- [x] 12.7 Temporal validity (active/superseded/stale/conflicted)
- [x] 12.8 Conflict-edge creation — **mechanism + symmetry + temporal** done; *semantic auto-detection (LLM) deferred* (flag).

## ⚠️ Design decisions & deferrals (flag for review)
1. **New `ProjectItem` node table** — the backlog said "item ingestion" without specifying the node model.
   I introduced `ProjectItem` as the graph node for requirements/assumptions/documents/decisions. Decisions
   also live in `DecisionRecord` (CP-11); their **logical id is the shared graph node id**, so edges can
   point at decisions. If you'd prefer a different node model, flag it now (before CP-13 builds on it).
2. **LLM-gated deferrals** (consistent with Phase-1 stub-vs-real): implicit/semantic edge extraction (12.4)
   and semantic conflict detection (12.8) need the real LLM; the deterministic **mechanism, integrity, and
   temporal layers are complete and tested**. The LLM layer lands with the real provider (same pattern as
   knowledge/verification placeholders).
3. **OD-1 (embedding model)** — using the deterministic stub (EMBED_DIM=8) now; real model + true dimension
   still open.

## Test evidence
- New: `test_embeddings.py` (3), `test_graph_builder.py` (5), `test_ingestion.py` (4), `test_api_items.py` (2).
- Full gate: **152 passed** (was 138), ruff clean, contracts OK.

## Next
CP-13 — **Retriever** (🔴 human gate). I will pause for your sign-off before merging CP-13, per the plan.

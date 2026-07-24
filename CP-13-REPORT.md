# CP-13 Report — Retriever (core, accuracy-critical)

**Status:** ✅ Complete (deterministic core; LLM parts deferred) · **Branch:** `cp-13` → `develop`
**Gate:** 🔴 human — you signed off to proceed; flagged items below for your review.

## What was built
The Retriever — "the LLM never searches the project; the Retriever does." `{project_id, question}` → relevant
context assembled from the project, fed to reasoning.

- **`engines/retrieval.py`** (stub → implemented):
  - Anchor extraction — explicit id refs (regex) + top dense hits as semantic anchors.
  - Dense — pgvector **cosine kNN** over `DocumentChunk` embeddings.
  - Lexical — query-term overlap (catches part numbers / exact terms embeddings miss).
  - Graph — **weighted seeded traversal + N-hop expansion** (edge-weight × hop-decay), surfaces linked
    decisions and conflicts.
  - Recency — exponential time decay.
  - **Temporal validity → confidence signal** (active .9 / conflicted .5 / stale .3 / superseded .2) — stale
    items rank down ("trust now").
  - **Hard-constraint floor** — active requirements + open conflicts marked full-focus (must-see).
  - **Missing-context guard** — `coverage_ok()`; thin relevance → clarification, not blind reasoning.
  - Signals → existing **`rank_score`** (weighted fusion, OD-2 default) via the Context Engine.
- **`eval/retrieval_eval.py`** — recall@k / precision@k / MRR / nDCG + merge-gate (`gate_passes`).
- **API wiring** — `/v1/analyze {project_id, question}` now uses the Retriever (context_items still override);
  WS analyze too. Missing-context guard returns clarification.

## Tickets
- [x] 13.1 anchor · [x] 13.2 dense · [x] 13.3 lexical · [x] 13.4 graph+expansion · [x] 13.5 recency
- [x] 13.6 fusion (weighted rank_score) · [x] 13.8 floor · [x] 13.9 guard · [x] 13.11 API wire · [x] 13.12 eval
- [~] 13.7 — **compress present (ContextEngine), LLM/cross-encoder rerank deferred**
- [~] 13.10 — **agentic multi-hop deferred (P1, LLM)**

## ⚠️ Flags for your review (accuracy-critical CP)
1. **LLM-gated deferrals** (stub pattern): anchor **LLM-fallback** (13.1), **rerank** (13.7), **agentic
   multi-hop** (13.10). The deterministic hybrid pipeline is complete + tested; these precision boosters land
   with the real LLM.
2. **OD-3 recall@k threshold = unset** (`RECALL_AT_K_GATE = None`) — gate disabled, no fabricated number
   (fail-safe, like the freeze gate). Needs a real gold set to derive. Eval harness is ready to measure.
3. **Floor vs compression** — compression (`token_budget`) isn't wired into the API path yet, so all
   retrieved candidates are currently kept (floor trivially satisfied). Full "floored items protected from
   compression" belongs with a compression-enable ticket.
4. **OD-2 fusion** — using weighted `rank_score` (default). **OD-4 rerank model**, **OD-10 edge weights** —
   using existing `RELATION_WEIGHTS` defaults; calibrate against the gold set later.

## Test evidence
- New: `test_retrieval.py` (6), `test_retrieval_eval.py` (4); updated `test_api.py`, `test_ws_and_live.py`
  to be DB-backed (analyze now uses the retriever).
- Full gate: **162 passed** (was 152), ruff 0.16.0 clean, contracts OK. CI-parity verified on py3.12.

## Next
CP-14 — Faithfulness / Grounding Gate (🔴 human, P0). Will pause for sign-off.

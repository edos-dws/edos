# CP-15 Report — Interactive Resolution + Write-back

**Status:** ✅ Complete (LLM re-reason deferred) · **Branch:** `cp-15` → `develop` · **Gate:** 🔴 human (under "run all gates" sign-off)

## Built
- **Write-back (Ch6 §11)** `engines/writeback.py`: on decision accept, `emit(DecisionAccepted)` + run jobs →
  `KnowledgeEngine.process` → ingest knowledge as graph nodes + embeddings. Accept now grows project knowledge.
- **Resolution** `engines/resolution.py`: `resolve_assumption` records the answer (`AssumptionResolution`
  table + alembic 0005), appends a new decision version with the matching freeze_blocker cleared;
  `resolve_conflict` closes `conflicts_with` edges and restores node validity.
- **API:** accept wired to write-back; `POST /v1/decisions/{id}/assumptions/resolve`,
  `POST /v1/conflicts/resolve`, `POST /v1/analyze/answer` (clarification loop — answers folded as context, re-run).

## Tickets
- [x] 15.1 assumption state (envelope table) · [x] 15.2 resolve assumption · [x] 15.3 resolve conflict
- [x] 15.4 clarification loop · [x] 15.5 write-back

## Flags
- **LLM re-reason deferred**: resolving an assumption clears its blocker + versions the decision
  deterministically; full LLM re-reasoning on the resolved state lands with the real model (stub pattern).
- Assumption resolution stored in an **envelope table**, not the locked decision contract (same purity stance
  as CP-11).

## Tests
+7 (writeback 1, resolution 3, api 3). Full gate: 174 passed, ruff clean.

## Next
CP-16 — Verification Hardening + Freeze (freeze threshold T stays data-derived / disabled — no fabrication).

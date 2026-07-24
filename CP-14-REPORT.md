# CP-14 Report — Faithfulness / Grounding Gate (P0)

**Status:** ✅ Complete (deterministic; semantic NLI deferred) · **Branch:** `cp-14` → `develop` · **Gate:** 🔴 human (proceeding under your "run all gates" sign-off)

## Built
- `engines/faithfulness.py`: `check()` traces every evidence source to the retrieved context (ref ids);
  `apply_gate()` scales confidence by faithfulness (never raises) and records ungrounded claims as
  `freeze_blockers`. Metrics: faithfulness_score, citation_precision.
- Wired into `/v1/analyze`: after reasoning, the gate runs against retrieved context; ungrounded → lowered
  confidence + freeze_blockers (kept contract-valid; `additionalProperties:false` blocks extra fields, so the
  "review" signal lives in freeze_blockers/confidence, not a new status).

## Tickets
- [x] 14.1 grounding check · [x] 14.2 gate action · [x] 14.3 metrics

## Flags
- **Deterministic evidence-source traceability** done. **Semantic per-claim NLI/LLM-judge (OD-5)** — does the
  context actually *support* the claim, not just cite it — is LLM-gated, deferred.
- `needs_review` is surfaced via confidence↓ + freeze_blockers (locked contract allows only
  proposed/recommended/verified/frozen). Numeric metrics available at engine level; surfacing in an API
  envelope is a later step (contract is additionalProperties:false).

## Tests
+5 (`test_faithfulness.py`). Full gate: 167 passed, ruff clean.

## Next
CP-15 — Interactive Resolution + Write-back.

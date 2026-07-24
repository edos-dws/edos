# CP-16 Report — Verification Hardening + Freeze

**Status:** ✅ Complete (real critic LLM + T-derivation deferred/data) · **Branch:** `cp-16` → `develop` · **Gate:** 🔴 human

## Built
- **Verify hardening (16.1)**: `VerificationEngine.verify(decision, context_refs=…)` runs the faithfulness
  pass (CP-14) — ungrounded evidence becomes issues; `Verdict.faithfulness` reported. Still lower-only
  confidence, freeze_blockers preserved. `/v1/verify` accepts optional `context_refs`.
- **Freeze (16.2/16.3)**: `POST /v1/decisions/{id}/freeze` runs `FreezeGate` with open-contradiction count
  from the graph. **Threshold T unset → gate disabled → freeze refused** (returns reasons). No autonomous freeze.

## Tickets
- [x] 16.1 Self-RAG critic (faithfulness-aware verify) · [x] 16.2 freeze threshold (T unset, fail-safe)
- [x] 16.3 freeze flow (gated endpoint)

## Flags (no fabrication)
- **OD-6 freeze threshold T = unset** — must be derived from scored benchmark runs (STOP condition). Freeze
  stays disabled until then. The gate + endpoint are ready; enabling is a data task + human decision.
- **Real independent critic LLM deferred** — verify's semantic critique is still the deterministic structural
  + faithfulness pass; the adversarial LLM critic lands with the real model.

## Tests
+5 (`test_cp16_verify_freeze.py`). Full gate: 178 passed, ruff clean.

## Next
CP-17 — Feedback / Learning loop.

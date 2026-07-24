# CP-17 Report — Feedback / Learning loop

**Status:** ✅ Complete · **Branch:** `cp-17` → `develop` · **Gate:** self-merge

## Built
- `DecisionOutcome` table (+ alembic 0006): outcome (accepted/challenged/reversed) + confidence snapshot.
- `engines/feedback.py`: `record_outcome`, `calibration_report` (mean confidence accepted vs reversed →
  `calibration_gap`; positive = well-calibrated), `suggest_ranking_adjustment` (advisory, eval-gated).
- API: `POST /v1/decisions/{id}/outcome`, `GET /v1/calibration`.

## Tickets
- [x] 17.1 outcome capture · [x] 17.2 confidence calibration · [x] 17.3 ranking tuning (advisory, eval-gated)

## Flags
- **Ranking auto-tuning is advisory only** — surfaced, never auto-applied, because retrieval-quality changes
  must pass the recall eval (OD-3 threshold unset). Conservative by design (no silent regressions).

## Tests
+5 (`test_feedback.py`). Full gate: 183 passed, ruff clean.

## Next
CP-18 — Frontend / UX (default stack; OD-7 flagged).

# CP-8 Report — Evaluation Harness

**Status:** ✅ Self-merged into `develop` · **Date:** 2026-07-22

## Built (9.1)
`score_run(rubric, scores)` scores a benchmark run: total, critical criteria (must be maxed),
hard-fail-if-zero (hallucination), pass/fail + reasons. `EDOS_BENCHMARK_RUBRIC` encodes the 10 criteria from
`concept-dry-run/scenarios/Scenario-02 — Evaluation Key` (pass ≥16/20; traps 1–3 critical).

## Tests
`74 passed` · ruff clean. Perfect run = 20/20 pass; a critical trap at 1 fails despite total 19; hallucination
zero hard-fails; below-16 fails.

## Why this matters for CP-9
This harness produces the **scored data** from which the freeze threshold `T` must be *derived* — so CP-9
does not guess it. Real run outputs come from live-LLM benchmark runs at go-live.

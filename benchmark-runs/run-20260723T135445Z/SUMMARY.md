# EDOS Live Benchmark Run — 20260723T135445Z

- Provider: **GeminiProvider** · Model: **gemini-3.6-flash** (Google AI Studio free tier)
- Scenarios attempted: 1 · scored: 1
- Judge: independent LLM pass over the scenario traps; harness = `edos.eval.harness.score_run`.

| Scenario | Score | Pass | Notes |
|----------|:-----:|:----:|-------|
| LMFP Cell BMS | 20/20 | True |  |

**Mean score:** 20.0 / 20  ·  **Passed:** 1/1

> Caveat: EDOS emits ONE contract-valid decision per scenario (not a 31-turn prose session), so a
> single decision may not surface all traps. These scores are directional go-live evidence; the
> freeze threshold T should be set from a stable, larger set of scored runs (ideally on a paid key
> with a Pro frontier model). Freeze stays DISABLED until then.

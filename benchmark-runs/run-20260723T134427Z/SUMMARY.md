# EDOS Live Benchmark Run — 20260723T134427Z

- Provider: **GeminiProvider** · Model: **gemini-3.6-flash** (Google AI Studio free tier)
- Scenarios attempted: 5 · scored: 2
- Judge: independent LLM pass over the scenario traps; harness = `edos.eval.harness.score_run`.

| Scenario | Score | Pass | Notes |
|----------|:-----:|:----:|-------|
| Solar LoRaWAN Agri Node | 20/20 | True |  |
| Edge AI Camera (InnoFusion) | — | ERROR | ConnectError: [Errno 101] Network is unreachable |
| Outdoor PTZ Camera (umbrella) | — | ERROR | ConnectError: [Errno 101] Network is unreachable |
| LMFP Cell BMS | — | ERROR | ConnectError: [Errno 101] Network is unreachable |
| Home Zone-Detection Gateway | 20/20 | True |  |

**Mean score:** 20.0 / 20  ·  **Passed:** 2/2

> Caveat: EDOS emits ONE contract-valid decision per scenario (not a 31-turn prose session), so a
> single decision may not surface all traps. These scores are directional go-live evidence; the
> freeze threshold T should be set from a stable, larger set of scored runs (ideally on a paid key
> with a Pro frontier model). Freeze stays DISABLED until then.

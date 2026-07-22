# CP-4 Report — Decision Engine (on stub LLM)

**Status:** ✅ Self-merged into `develop` · **Date:** 2026-07-22

## What was built
| Ticket | Delivered |
|--------|-----------|
| 5.1 | `DecisionEngine.analyze(context)` — reasons only over the context package (never retrieves), routes through the Model Router, returns a contract-valid `Decision`. **Status capped at `recommended`** (verified/frozen downgraded — no autonomous freeze here). |
| 5.2 | **Clarification policy** — empty/insufficient context returns `ClarificationNeeded` (with questions) instead of a fabricated decision. |

## Test evidence
```
53 passed · ruff clean
Key: valid decision emitted + capped at recommended; a provider returning "frozen" is downgraded;
     empty context yields clarification, not a guess.
```

## Important — this is on the STUB LLM
Per backlog 5.1 ("reason via model_router **stub**"), CP-4 is built on the deterministic stub — no live model,
no API key needed. The **real-LLM connection + prompt content** is a separate **go-live step** that will need:
- your **LLM provider choice** (Anthropic/Claude recommended) and an **API key** (stored as a secret), and
- prompt-content authoring + a review of real output.

I'll flag that go-live step explicitly; it is not silently skipped.

## Next
CP-5 (Verification Engine — the safety spine) also runs on the stub and can proceed.

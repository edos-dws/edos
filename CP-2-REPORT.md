# CP-2 Report — Model Router + Prompt Layer (stubbed LLM)

**Status:** 🔵 Awaiting human approval · **Branch:** `cp-2` · **Date:** 2026-07-22

## What was built (no live LLM — all stubbed)

| Ticket | Delivered |
|--------|-----------|
| 3.1 | **Model Router** — `Capability`/`Tier` enums + the Ch 4 capability→tier table; provider-abstract `Provider` protocol; `StubProvider` returning deterministic, schema-valid fixtures; `ModelRouter.execute(capability, context, schema)` |
| 3.2 | **Prompt Registry** — versioned `PromptSpec` (purpose, compatible models, output schema, token budget); seeded planner/decision/verification/knowledge prompts; every `output_schema` validated against the locked contracts |
| 3.3 | **Validate → repair → fallback → reject loop** — `produce_valid()`; the router repairs malformed output, falls back, and raises `MalformedOutputError` if nothing validates. **Malformed output is never returned or persisted** (Ch 9) |

## Test evidence
```
38 passed · ruff clean
Key: decision capability returns contract-valid JSON; malformed provider output is repaired on retry;
     never-valid output is rejected (MalformedOutputError), not returned.
```

## What YOU validate at this gate
1. **The abstraction is right** — is routing-by-capability (not vendor) the shape you want? See the
   `CAPABILITY_TIER` table and `Provider` protocol.
2. **No live LLM leaked in** — confirm CP-2 is entirely stubbed (real providers are deliberately deferred to CP-4).
3. **The safety behavior** — malformed model output is repaired-or-rejected, never persisted (`test_repair_loop.py`).

## Notes / deferred (flagged, not silently skipped)
- **Prompt *content* is intentionally empty** — the registry holds metadata only. Actual prompt text is
  authored and tuned at **CP-4** (first live LLM), exactly as planned.
- **Model names in the registry** (`claude-opus-4-8`, `gpt-5`, …) are placeholders for the tier mapping;
  the real provider bindings + API keys land at CP-4.

## Next on approval
Merge `cp-2` → `main`, mark CP-2 ✅. Then **CP-3** (Context Engine — deterministic assembly + ranking formula).

# Prompts + Benchmarks — Overnight Build Report (for review together)

**Branch:** `feat-prompts-benchmarks` → merged to `develop` · **Date:** 2026-07-23 · **Gate:** 90 tests green

Built the two pre-go-live steps. **No live LLM used — everything here is authoring + wiring, ready for the
real model tomorrow.** The prompt is written **generic for embedded systems** (the 4–5 domain runs are only
*validation* — nothing is hard-coded to them; a test enforces no domain lock-in).

---

## Step 1 — Production prompt suite (the "prompt engine")

Location: `src/edos/prompts/templates/`, wired through the registry (`decision_prompt:v1`, etc.).

- **`erc_core.md`** — one shared block of generic senior-embedded reasoning principles (truth discipline,
  never-invent-data, cross-domain ripples, contradiction detection, calculation, confidence calibration,
  push critical assumptions back with consequences). Substituted into the reasoning prompts via `{{ERC_CORE}}`
  so the principles live in ONE place and stay maintainable.
- **`decision_prompt.v1.md`** — reasons over a context package and returns **strict `edos.decision.v1` JSON**.
  Maps ERC reasoning onto every field (assumptions with confidence + risk_if_wrong; freeze_blockers for
  unresolved critical inputs; status always `recommended`; never guess a missing datasheet value — ask via
  `next_actions`).
- **`verification_prompt.v1.md`** — critique-not-regenerate; confidence only ever lowered; skeptical when
  uncertain.
- **`planner_prompt.v1.md`**, **`knowledge_extraction_prompt.v1.md`** — lightweight routing + structured
  knowledge extraction.

Registry now loads real template text (`load_template(ref)`); template quality-gate tests assert the
non-negotiables are present and that the prompt is **not over-fit to any domain**.

## Step 2 — Benchmark dataset

Location: `benchmarks/scenario-02..06.json`, loaded by `src/edos/eval/benchmarks.py` into the CP-8 harness.

- Each scenario pairs its **intake reference + the traps a good run must catch** with a **generic
  embedded-reasoning rubric** (10 dimensions, 0–2 each, pass ≥16/20): factual_correctness +
  contradiction_detection are **critical** (must be maxed); no_hallucination **hard-fails at 0**; plus
  calculation_quality, assumption_tracking, cross_domain_awareness, confidence_calibration, freeze_discipline,
  decision_support, over_engineering_check.
- Tests prove every benchmark loads, a perfect run passes, missing a critical dimension fails, and
  hallucination hard-fails — across all five scenarios.

---

## Decisions I made (please sanity-check these tomorrow)
1. **Reasoning → JSON.** The runs are rich prose; the Decision Engine needs machine-readable output. The
   prompt keeps the ERC *reasoning behaviour* but emits the locked JSON contract. This is the ERC↔schema
   reconciliation flagged early on.
2. **Generic rubric, not per-domain.** One embedded-wide rubric applies to all scenarios; scenario-specific
   `traps` are listed separately and (at go-live) an **LLM-judge** decides whether each trap was caught.
3. **Verification/knowledge/planner output_schema = "none"** (their outputs aren't the decision contract).
   Only `decision_prompt` targets `edos.decision.v1`.

## Open questions for us tomorrow
- Prompt tone/length — happy to tighten or expand once we see real model output.
- The trap→score mapping at go-live: LLM-judge vs a human pass for the first calibration runs?
- Whether to add more scenarios (different embedded domains) before deriving the freeze threshold `T`.

## Still gated on go-live (Step 3, with the API key)
Swap `StubProvider` → real provider, run these scenarios live, score with the harness, tune the prompt, and
**derive `T`** from the scores. Autonomous freeze stays **OFF** until then.

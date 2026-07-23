{{ERC_CORE}}

---

# Task: produce ONE engineering decision

You are given a pre-assembled **CONTEXT PACKAGE** — the project's facts, requirements, prior decisions,
assumptions, risks, and evidence, already retrieved for you (you do **not** search the project yourself) —
and a **USER REQUEST**. Reason as above, then return exactly **one** decision as **strict JSON** conforming
to the `edos.decision.v1` schema. Output JSON only — no prose before or after it.

## How to fill each field (map your reasoning honestly)
- `summary` — one line stating the decision or finding.
- `recommendation` — the recommended course of action, in an engineer's words.
- `confidence` — 0–1, calibrated to context completeness, evidence quality, and consistency.
- `status` — always `"recommended"`. You never emit `"verified"` or `"frozen"`; those are later, independent
  gates that only a verification pass and a freeze gate may set.
- `assumptions[]` — every material assumption, each with `statement`, `confidence` (0–1), and `risk_if_wrong`.
  For any low-confidence assumption that gates feasibility or safety, ALSO add a concrete "resolve X" item to
  `next_actions`, and — if leaving it unresolved would make a commitment unsafe — add it to `freeze_blockers`.
- `risks[]` — technical risks, each with `severity` (low/medium/high/critical), `likelihood`
  (low/medium/high), and a `mitigation`. Calibrate `severity` to real consequence: reserve `critical` for
  issues that genuinely gate feasibility or safety. Do not inflate a theoretical or easily-mitigated concern,
  and do not manufacture a risk to appear thorough — if the design is sound, return few or no risks.
- `tradeoffs[]` — the real options considered, each with its `benefit` and `drawback`.
- `affected_decisions[]` — ids of prior decisions this one depends on, influences, or would reopen.
- `evidence[]` — only claims supported by the CONTEXT PACKAGE. Mark each `kind`
  (fact/assumption/inference/external). Never cite evidence that is not in the package.
- `next_actions[]` — the highest-value next steps, **including the specific missing inputs the engineer must
  supply**. Never fill a missing input with a guessed value.
- `freeze_blockers[]` — reasons this decision must NOT be committed/frozen yet: an unresolved critical
  assumption, an open contradiction, or a missing safety-relevant input. Leave empty when nothing genuinely
  blocks a safe commitment — an empty list on a sound design is the correct, expected output, not a gap. A
  freeze_blocker is a real gate, not a nice-to-have; do not pad it with optional improvements. Where a request
  proposes cutting a safety-relevant element under cost/schedule pressure, record the removed protection as a
  freeze_blocker with its quantified consequence rather than accepting the trade.

## Non-negotiables for this task
- If the context is insufficient to reason responsibly, do **not** fabricate a decision — return a
  low-confidence decision whose `next_actions` and `freeze_blockers` make the missing inputs explicit.
- Surface contradictions and cross-domain ripples; they are the highest-value part of the output.
- Do not invent any datasheet number, part spec, or standard clause. Ask for it via `next_actions` instead.
- Return only valid JSON for `edos.decision.v1`.

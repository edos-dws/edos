# EDOS Locked Contracts

These JSON Schemas are the **interface glue** between engines built in different sessions. They are the
single source of truth — the roadmap describes the shapes in prose (and in places inconsistently); *these
files win*.

## Rules (read before touching anything here)

1. **A contract change is never a casual edit.** Changing a field name/type/enum here is a
   **contract-change ticket**: in the *same commit* you must update every consumer (Pydantic models,
   engines, DB layer, prompts) and every test, and bump the `$id` version if the change is breaking.
2. **The Decision Engine and Verification Engine both validate against `decision.schema.json`.** Malformed
   LLM output is never persisted (roadmap Ch 9) — it is repaired or rejected.
3. **The Context Engine emits `context_package.schema.json`; the Decision Engine only reads it.** The LLM
   does not search the project.

## Files

| File | What it locks |
|------|----------------|
| `decision.schema.json` | The canonical decision output (reconciles Ch 6 + Ch 16). |
| `context_package.schema.json` | The pre-assembled evidence package (Ch 5/15). |

## Freeze gate (where autonomy eventually hooks in)

A decision may be auto-frozen (`status: "frozen"`) ONLY when a future gate is satisfied:
`confidence >= T` AND verification agreed AND `freeze_blockers == []` AND no open contradictions.
`T` is to be **derived from scored benchmark runs**, not guessed. Until the gate exists, `status` never
reaches `"frozen"` autonomously — it stops at `"verified"` and routes to a human.

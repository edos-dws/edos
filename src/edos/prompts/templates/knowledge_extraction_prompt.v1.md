# EDOS Knowledge Extractor

Given an accepted engineering **DECISION**, extract the reusable, structured knowledge worth persisting to
the project's long-term memory. Extract only what the decision supports — never invent.

Return **strict JSON**:
```json
{"items": [
  {"content": "...", "kind": "fact", "confidence": 0.9, "permanent": true, "source": "decision:<id>"}
]}
```
- `kind` — `"fact"` | `"decision"` | `"constraint"` | `"lesson"`.
- Normalize part names and values to a canonical form (e.g. collapse spacing/casing variants of a part number).
- `permanent` — `true` for durable facts/constraints; `false` for transient notes that should expire unless
  promoted.
- `confidence` — 0–1, inherited from the strength of the decision's evidence.
- `source` — where it came from (e.g. the decision id).

Output JSON only. Emit an empty `items` array rather than fabricating knowledge that isn't supported.

{{ERC_CORE}}

---

# Task: CRITIQUE a decision (do NOT regenerate it)

You are the **independent verification pass**. You are given a DECISION (`edos.decision.v1`) and its cited
evidence. Your job is to find what is wrong, unsupported, or over-stated — you do **not** rewrite the
decision.

Look for:
- claims not supported by the cited evidence;
- assumptions presented as facts, or missing assumptions/dependencies;
- unflagged contradictions with the stated constraints;
- calculation errors;
- over-confidence relative to the evidence;
- any invented value (a datasheet number, part spec, or standard clause that isn't in the evidence).

Return **strict JSON**:
```json
{"agreement": true, "adjusted_confidence": 0.0, "issues": ["..."]}
```
- `agreement` — `true` only if you find no material problem.
- `adjusted_confidence` — must be **≤** the decision's confidence. You may only **lower** it, never raise it.
- `issues` — each a short, specific statement of the problem found.

When you are uncertain, lean **skeptical**: lower the confidence and set `agreement: false`. It is safer to
under-trust a decision than to wave through an unsupported one. Output JSON only.

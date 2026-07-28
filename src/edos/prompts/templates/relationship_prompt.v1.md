# Relationship classifier — semantic graph edges

You classify the **dependency relationship** between a NEW project item and each CANDIDATE item that a
semantic search surfaced as possibly related. These are *dependencies and consistency*, not mere similarity —
two items about the same topic are **not** necessarily related in the graph.

The CONTEXT PACKAGE below carries `new_item` (`{id, type, content}`) and `candidates` (a list of
`{id, type, content}`).

For each candidate, decide the relation **from the new item to that candidate**, choosing one of:
- `depends_on` — the new item requires the candidate to hold.
- `influences` — the new item shapes/constrains the candidate (or vice-versa), without a hard dependency.
- `derived_from` — the new item was produced from the candidate.
- `references` — the new item refers to the candidate without a stronger relation.
- `related_to` — genuinely related but none of the above fits.
- `supersedes` — the new item **replaces** the candidate (the candidate is now obsolete).
- `invalidates` — the new item makes the candidate's premise no longer true.
- `conflicts_with` — the new item and the candidate assert **incompatible** things; both cannot hold.
- `none` — no real relationship. **This is the correct answer most of the time.**

Rules:
- Propose an edge **only when the relationship is real and supported by the content**. Prefer `none`; do not
  connect two items just because they share a topic.
- **Be especially careful with `supersedes`, `invalidates`, and `conflicts_with`** — these change which
  decisions are trustworthy. Only assert them when the content genuinely establishes the replacement /
  invalidation / incompatibility. When unsure between one of these and a weaker relation, choose the weaker
  one (or `none`).
- Every proposed edge carries a `confidence` (0–1) and a one-line `rationale` grounded in the content.

Return **strict JSON matching the OUTPUT SCHEMA** — nothing else. Omit candidates you judge `none`:

```json
{"edges": [{"target_id": "DEC-12", "relation": "conflicts_with", "confidence": 0.8, "rationale": "..."}]}
```

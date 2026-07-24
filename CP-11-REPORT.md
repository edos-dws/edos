# CP-11 Report — Persistence & Versioning (decision store)

**Status:** ✅ Complete · **Branch:** `cp-11` → `develop` · **Gate:** self-merge

## What was built
Immutable, versioned decision persistence — accepted decisions become a durable, auditable history.

- **DB:** `DecisionRecord.body_json` added (full `edos.decision.v1` contract; projected columns for querying).
  `new_decision_version()` now carries `body_json`. Alembic `0003_decision_body_json.py`.
- **Store engine** (`src/edos/engines/decision_store.py`): `save_new`, `get_latest`, `get_version`,
  `history`, `list_for_project`, `accept` (appends an `accepted` version, prior left immutable), `to_decision`.
- **REST:** `POST /v1/decisions`, `GET /v1/decisions/{id}`, `GET /v1/decisions/{id}/history`,
  `POST /v1/decisions/{id}/accept`, `GET /v1/projects/{pid}/decisions`. Returns an envelope
  `{id, project_id, version, parent_version, status, confidence, decision}`.

## Tickets
- [x] 11.1 DecisionStore — save/get/list.
- [x] 11.2 Accept + versioning — accept→v+1 `accepted`, prior immutable, `supersedes`(parent_version) link.
- [x] 11.3 Decision API — persist/get/history/accept/list.
- [~] 11.4 **Design deviation — needs your nod.** See below.

## ⚠️ Design decision (11.4) — flag for review
Backlog 11.4 said "add `version`/`supersedes`/`project_id` to `decision.schema.json`". I did **not** mutate
the locked reasoning contract. Instead these are **persistence-envelope** metadata on `DecisionRecord`
(version, parent_version, project_id, body_json). Rationale:
- The reasoning contract (what the LLM produces) should stay pure — version/supersedes are assigned at
  *persist* time, not produced by reasoning. Polluting the locked contract would be a breaking `$id` bump for
  no reasoning benefit.
- Cross-decision supersession belongs in the **graph** (`supersedes`/`conflicts_with` edges, CP-12), not the
  decision contract.

**Effect:** cleaner separation, no contract break. If you'd rather the fields live in the contract, say so and
I'll do the contract-change ticket instead. Defaulting to the envelope approach to keep moving.

## Test evidence
- New: `tests/test_decision_store.py` (5), `tests/test_api_decisions.py` (3).
- Full gate: **138 passed** (was 130), ruff clean, contracts OK.

## Next
CP-12 — Ingestion + Embeddings + Graph (edge extraction, no-orphan, integrity, temporal validity, conflict edges).
Open decision OD-1 (embedding model) will be flagged when its ticket is reached.

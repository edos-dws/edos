# CP-1 Report — Domain Model + Persistence

**Status:** 🔵 Awaiting human approval · **Branch:** `cp-1` · **Date:** 2026-07-22

## What was built

**E1 — Domain model (Pydantic v2, bound to the locked contracts)**
| Ticket | Delivered |
|--------|-----------|
| 1.1 | `Decision` output model + `validate_against_contract()` — mirrors `contracts/decision.schema.json` (extra=forbid ↔ additionalProperties:false) |
| 1.2 | `ContextPackage`/`ContextItem` + `ranked_items()` — mirrors `contracts/context_package.schema.json` |
| 1.3 | Core entities (Project, Requirement, Assumption, Component, Risk, Document, KnowledgeItem, Alert) + `RelationType` (all 11) + `Edge` |

**E2 — Persistence (SQLAlchemy 2.0 + Postgres/pgvector, Ch 11/13)**
| Ticket | Delivered |
|--------|-----------|
| 2.1 | `DecisionRecord` with **immutable versioning** via `new_decision_version()` (append-only; original row untouched) |
| 2.2 | `GraphEdge` + `neighbors()` traversal + Ch 15 relation `weight_for()` |
| 2.3 | `DocumentChunk` with a pgvector `embedding` column + nearest-k (L2) retrieval |

## Test evidence

```
26 passed  (stdlib baseline + pytest) · ruff: All checks passed
4 DB tests ran against real Postgres+pgvector (not skipped): versioning, graph traversal, vector nearest-k
```
DB tests **skip** (not fail) if Postgres is unreachable; CI now runs a `pgvector/pgvector:pg16` service so they execute in CI too.

## ⭐ What YOU validate at this gate (the most important review in the build)

Everything downstream is built on these. Please confirm:

1. **The locked schemas capture what EDOS needs** — read `contracts/decision.schema.json` and
   `contracts/context_package.schema.json`. Right fields? Right enums (`status`: proposed/recommended/verified/frozen)?
   Is `freeze_blockers` the right hook for the CP-9 freeze gate? Anything missing you'll want to store/freeze?
2. **Decision versioning is immutable** — see `new_decision_version()` and `test_db_decisions.py`.
3. **Graph relation weights** — `RELATION_WEIGHTS` in `db/graph.py`.

## Scope notes / decisions needed from you (flagged, not silently skipped)

- **Alembic migrations deferred.** CP-1 creates tables via `create_all` (`db/schema.py`). Formal migrations
  are a small follow-up — OK to defer to CP-6, or want them now?
- **`DEFAULT_WEIGHT = 5.0`** — Ch 15 only weights 5 of the 11 relation types (depends_on/influences/
  invalidates/mitigates/related_to). The other 6 use a documented placeholder. Confirm or supply weights.
- **`EMBED_DIM = 8`** — placeholder vector dimension. Real value is set when the embedding model is chosen
  (CP-2/CP-3). No action now; noted so it isn't forgotten.

## How to review

```bash
git fetch origin && git checkout cp-1
./scripts/check.sh          # 26 green (DB tests run if Postgres is up)
$EDITOR contracts/          # the schemas to sign off
```

## Next on approval
Merge `cp-1` → `main`, mark CP-1 ✅ in `PROGRESS.md`. Then **CP-2** (Model Router + Prompt layer, stubbed LLM).

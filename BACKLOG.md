# EDOS Build Backlog

Work **top to bottom, one ticket at a time.** Check the box when the ticket's Definition of Done (see
`CLAUDE.md`) is met. Each ticket is scoped to be small enough to finish + test + commit in one pass.

Legend: `[ ]` todo · `[x]` done · each ticket has **Acceptance** (what must be true) and **Test** (what to assert).

---

## EPIC 0 — Foundation

- [x] **0.1 Repo scaffold + locked contracts + green baseline test**
  Acceptance: repo tree, `contracts/decision.schema.json` + `context_package.schema.json`, stdlib baseline
  test passing. Test: `python3 tests/test_contracts.py` exits 0. *(done at scaffold)*
- [x] **0.2 Dev environment**
  Acceptance: `pyproject.toml` installs cleanly; `pytest`, `pydantic>=2`, `fastapi`, `jsonschema`,
  `sqlalchemy`, `redis` available; `ruff` configured. Test: `python3 -m pytest tests/` runs and is green.
  *(done: `.venv` bootstrapped, `pip install -e .[dev]` clean on Py3.14, full gate green.)*
- [x] **0.3 CI-equivalent check script**
  Acceptance: `scripts/check.sh` runs lint + full test suite and exits nonzero on any failure.
  Test: script exists, runs green on current tree. *(done: venv-aware `check.sh` + GitHub Actions CI.)*

## EPIC 1 — Domain model & schema validation

- [ ] **1.1 Pydantic `Decision` model bound to `decision.schema.json`**
  Acceptance: `src/edos/models/decision.py` defines `Decision` (Pydantic v2) whose `.model_json_schema()`
  is a superset-compatible match of the locked contract; a helper validates dicts against the JSON Schema.
  Test: a valid decision passes; missing `evidence`/bad `confidence`/unknown `status` each fail.
- [ ] **1.2 `ContextPackage` model bound to `context_package.schema.json`** — analogous. Test: round-trips + rejects malformed.
- [ ] **1.3 Remaining core entities** (Project, Requirement, Assumption, Risk, Component, Document, Edge)
  per roadmap Ch 3. Test: construct each; graph `Edge` enforces the 11 relation types.

## EPIC 2 — Persistence (Ch 11, 13)

- [ ] **2.1 SQLAlchemy models + migrations** for the entities above; immutable/versioned decisions
  (parent_version, status, confidence). Test: insert a decision, create a new version, original unchanged.
- [ ] **2.2 Decision Graph edges** (source_id, target_id, relation_type, confidence). Test: traverse
  depends_on from a node; weights match Ch 15 (depends_on=10 … related_to=3).
- [ ] **2.3 pgvector document_chunks** (embedding column, 300–700 token chunks). Test: store + nearest-k stub.

## EPIC 3 — Model Router & Prompt layer (Ch 4, 9, 16)

- [ ] **3.1 `model_router.execute(capability, context, schema)`** provider-abstract interface; **stubbed**
  to return schema-valid fixtures (no live LLM). Test: returns a `decision`-schema-valid object for the
  decision capability; tier selection table (Ch 4) maps task→tier.
- [ ] **3.2 Prompt registry** (`src/edos/prompts/`) with versioned entries (`decision_prompt:vX`), each with
  purpose/compatible-models/output-schema metadata. Test: registry lookup + every prompt names a valid schema.
- [ ] **3.3 JSON validation + repair loop** (Ch 9): validate → repair-retry → fallback → reject; malformed
  never persisted. Test: malformed fixture is repaired or rejected, never written.

## EPIC 4 — Context Engine (Ch 5, 15)

- [ ] **4.1 Deterministic pipeline skeleton** intent→entities→plan→graph→rules→semantic→rank→compress→assemble,
  emitting a valid `context_package`. Test: given fixture project data, output validates + is ranked desc.
- [ ] **4.2 Ranking formula** `0.40*graph + 0.30*semantic + 0.15*recency + 0.10*confidence + 0.05*focus`.
  Test: known inputs produce the hand-computed score/order.
- [ ] **4.3 Rule expansion** (deterministic, no LLM): MCU→drivers/bootloader/clock/power; battery→power budget.
  Test: an MCU-change entity expands to the required related items.

## EPIC 5 — Decision Engine (Ch 6)

- [ ] **5.1 Decision pipeline**: consistency-check → reason (via model_router stub) → assemble a
  `decision`-valid object; **status caps at `recommended`**. Test: consumes a `context_package`, emits valid
  decision; never sets `frozen`.
- [ ] **5.2 Clarification policy**: if essential info missing, return a "needs_clarification" outcome instead
  of guessing. Test: a context package missing a required field yields clarification, not a fabricated value.

## EPIC 6 — Verification Engine (Ch 6, 18) — the safety spine

- [ ] **6.1 Verification pass**: takes (request, decision, evidence), **critiques (does not regenerate)**,
  returns agreement + adjusted confidence + found issues; can only *lower* confidence. Test: an unsupported
  claim lowers confidence and sets agreement=false.
- [ ] **6.2 Status promotion**: `recommended`→`verified` only if verification agrees; populate
  `freeze_blockers` otherwise. Test: disagreement blocks promotion and records blockers.

## EPIC 7 — API & pipelines (Ch 10, 14)

- [ ] **7.1 FastAPI app** with `/v1/ask`, `/v1/analyze`, `/v1/verify` wired to the engines. Test: `/v1/analyze`
  returns a `decision`-schema-valid body for a fixture project.
- [ ] **7.2 Async passive pipeline** (DecisionAccepted → summary/embeddings/graph-update jobs) on a queue.
  Test: emitting the event enqueues the expected jobs.

## EPIC 8 — Knowledge Engine (Ch 7)

- [ ] **8.1 Extraction → normalization → quality gates → graph write.** Test: a decision produces structured
  knowledge that passes the quality gates (schema/refs/dedupe/confidence/attribution) before persist.

## EPIC 9 — Freeze gate & evaluation (Ch 12) — DO LAST, NEEDS DATA

- [ ] **9.1 Evaluation harness** to score benchmark runs against a rubric (see the `concept-dry-run`
  scenarios + Evaluation Keys). Test: scoring a fixture run yields the expected rubric total.
- [ ] **9.2 Freeze gate** `confidence>=T AND verified AND freeze_blockers==[] AND no open contradictions`.
  **T is BLOCKED** until derived from scored runs — do not invent it (STOP condition). Test: gate refuses to
  freeze when any clause fails; with T undefined, freeze is disabled.

---

### Notes log (agent appends one line per finished ticket)
- 0.1 — scaffold + contracts + stdlib baseline test committed.

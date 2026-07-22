# EDOS Build Progress Tracker

**Single source of truth for status.** The runner (Claude Code) updates this file; the human reads it to
know what's done, what's next, and what's waiting on them. This file tracks *state*; the detailed *plan*
lives in [`BUILD_PLAN.md`](./BUILD_PLAN.md) and the *tickets* in [`BACKLOG.md`](./BACKLOG.md).

> **Runner:** update this file as part of every ticket's Definition of Done and at every gate (see the
> Update Protocol at the bottom). Keep "Current State" and "Human Action Queue" accurate — they are what the
> human reads first.

---

## Current State  ⟵ runner keeps this current

| Field | Value |
|-------|-------|
| Current checkpoint | **CP-1 — Domain model + persistence** (🟡 in progress on `cp-1`) |
| Current ticket | CP-1 complete → building PR |
| Build gate | 🟢 GREEN (`scripts/check.sh`: stdlib + pytest + ruff) |
| Infra | 🟢 Postgres 16.14 (pgvector ON) :5432 · Redis :6379 — both healthy |
| Blocked? | No |
| Waiting on human? | No — next human gate at CP-1 completion (schema-lock review) |
| Repo | https://github.com/edos-dws/edos (`main` @ CP-0 ✅; work on `cp-1`) |
| Last updated | 2026-07-22 (CP-0 approved; CP-1 started) |

---

## Human Action Queue  ⟵ what needs YOU right now

- [x] ~~Create GitHub repo~~ — https://github.com/edos-dws/edos.
- [x] ~~Bring up infra~~ — Postgres+pgvector :5432, Redis :6379, healthy.
- [x] ~~Approve CP-0~~ — **locked in 2026-07-22.**
- [x] ~~Git-as-gate flow~~ — **confirmed:** CP-branch → PR → human merge.
- [x] ~~Runner location~~ — **confirmed:** this machine (Claude Code).
- [ ] **Next gate — CP-1:** when the `cp-1` PR opens, review the locked schemas (`contracts/`) + decision versioning.

*(Runner: as gates are reached, replace this list with the specific thing the human must validate for that CP.)*

---

## Checkpoint Tracker

Status: ⬜ not started · 🟡 in progress · 🔵 awaiting human review · ✅ approved · 🔴 blocked

| CP | Milestone | Status | Branch / PR | Human validates | Signed off |
|----|-----------|:------:|-------------|-----------------|:----------:|
| CP-0 | Setup, repo, CI, infra | ✅ | `main` (see `CP-0-REPORT.md`) | repo on GH · CI green on a PR · Postgres+Redis reachable · runner can push | ☑ 2026-07-22 |
| CP-1 | Domain model + persistence | 🟡 | `cp-1` | schemas capture intent; decision versioning immutable; graph weights | ☐ |
| CP-2 | Model router + prompt layer (stubbed) | ⬜ | — | abstraction clean; validate/repair; no live LLM | ☐ |
| CP-3 | Context engine | ⬜ | — | ranking order correct; LLM doesn't search the project | ☐ |
| CP-4 | Decision engine | ⬜ | — | real scenario → valid decision; **first prompt tuning** | ☐ |
| CP-5 | Verification engine (safety spine) | ⬜ | — | critiques not regenerates; only lowers confidence | ☐ |
| CP-6 | API + pipelines | ⬜ | — | `/v1/analyze` end-to-end | ☐ |
| CP-7 | Knowledge engine | ⬜ | — | quality gates before persist | ☐ |
| CP-8 | Evaluation harness | ⬜ | — | scores dry-run scenarios vs Evaluation Keys | ☐ |
| CP-9 | Freeze gate | ⬜ | — | `T` derived from CP-8 scores; unsafe freezes refused | ☐ |

---

## Ticket Tracker

Mirrors [`BACKLOG.md`](./BACKLOG.md). Runner updates status + commit hash per ticket.

| Ticket | Status | Commit | Note |
|--------|:------:|--------|------|
| 0.1 Scaffold + contracts + baseline | ✅ | `0e4c241` | done at scaffold |
| 0.2 Dev environment | ✅ | (venv) | `.venv`+pip bootstrapped; deps clean on Py3.14; gate green |
| 0.3 CI-equivalent check script | ✅ | `0c1b3c1` | `scripts/check.sh` + Actions CI |
| 1.1 Decision Pydantic model | ✅ | `cp-1` | bound to contract; 8 tests (enum/range/extra/missing) |
| 1.2 ContextPackage model | ✅ | `cp-1` | bound to contract; ranked_items() + 6 tests |
| 1.3 Core entities + graph edges | ✅ | `cp-1` | 8 entities + 11-type RelationType + Edge; 5 tests |
| 2.1 SQLAlchemy models + migrations | ✅ | `cp-1` | DecisionRecord + new_decision_version(); immutable-version test (ran vs PG) |
| 2.2 Decision Graph edges | ✅ | `cp-1` | GraphEdge + neighbors() + Ch15 weights |
| 2.3 pgvector document_chunks | ✅ | `cp-1` | DocumentChunk(Vector) + nearest-k L2 |
| 3.1 model_router (stubbed) | ⬜ | — | schema-valid fixtures |
| 3.2 Prompt registry | ⬜ | — | versioned entries |
| 3.3 JSON validate + repair loop | ⬜ | — | never persist malformed |
| 4.1 Context pipeline skeleton | ⬜ | — | emits valid context_package |
| 4.2 Ranking formula | ⬜ | — | 0.40/0.30/0.15/0.10/0.05 |
| 4.3 Rule expansion | ⬜ | — | deterministic, no LLM |
| 5.1 Decision pipeline | ⬜ | — | caps at `recommended` |
| 5.2 Clarification policy | ⬜ | — | no guessing |
| 6.1 Verification pass | ⬜ | — | critique, lower-only |
| 6.2 Status promotion | ⬜ | — | records freeze_blockers |
| 7.1 FastAPI endpoints | ⬜ | — | /v1/analyze |
| 7.2 Async passive pipeline | ⬜ | — | event fan-out |
| 8.1 Knowledge extraction + gates | ⬜ | — | Ch 7 |
| 9.1 Evaluation harness | ⬜ | — | rubric scoring |
| 9.2 Freeze gate | ⬜ | — | **T blocked until CP-8 data** |

---

## Blockers Log

*(Runner: when a STOP condition hits, add a row here and also write detail to `BLOCKED.md`. Do not guess past it.)*

| Date | Ticket | Blocker | Needs |
|------|--------|---------|-------|
| — | — | none | — |

---

## Activity Log  (append-only, newest at top — one line per event)

- 2026-07-22 — CP-1 t2.1/2.2/2.3: persistence layer (SQLAlchemy Base/engine, DecisionRecord immutable versioning, GraphEdge traversal+Ch15 weights, pgvector DocumentChunk nearest-k). 4 DB tests ran vs Postgres; CI got a pgvector service. 26 tests green. E2 complete.
- 2026-07-22 — CP-1 t1.3: domain entities (Project/Requirement/Assumption/Component/Risk/Document/KnowledgeItem/Alert) + `RelationType` (11) + `Edge`; 5 tests green. Model layer (E1) complete.
- 2026-07-22 — CP-1 t1.2: `ContextPackage`/`ContextItem` bound to `context_package.schema.json`; `ranked_items()`; 6 tests green.
- 2026-07-22 — CP-1 t1.1: `Decision` model + `validate_against_contract()` bound to `decision.schema.json`; 8 tests green.
- 2026-07-22 — **CP-0 APPROVED / locked in.** Defaults confirmed: git-as-gate flow (branch→PR→merge), runner on this machine. Started CP-1 on branch `cp-1`.
- 2026-07-22 — CP-0 complete: `.venv`+pip bootstrapped (Py3.14), deps installed, Postgres+pgvector & Redis up & healthy, full gate green (pytest+ruff). CP-0 → 🔵 awaiting approval; report in `CP-0-REPORT.md`.
- 2026-07-22 — Repo pushed to https://github.com/edos-dws/edos over SSH (`main` @ `5faed77`). CI live on next PR/push. Awaiting human infra bring-up + CP-0 approval.
- 2026-07-22 — CP-0 foundation + local infra + CI committed (`0e4c241`, `0c1b3c1`). Awaiting GitHub repo + human infra bring-up.

---

## Update Protocol (for the runner)

**After each ticket (part of Definition of Done):**
1. Set the ticket's row to ✅ and record the commit hash + a one-line note.
2. Update **Current State** (current ticket → next todo; build gate color).
3. Prepend one line to the **Activity Log**.

**At a checkpoint gate:**
1. Set the CP row to 🔵 *awaiting human review*, fill in the branch/PR.
2. Rewrite the **Human Action Queue** to the exact thing(s) the human must validate for this CP.
3. Write `CP-N-REPORT.md` (what was built, test evidence, blockers) and reference it in the Activity Log.
4. **Stop. Do not start the next checkpoint until the human sets the CP to ✅ and merges the PR.**

**On a blocker (STOP condition):**
1. Set Current State `Blocked? = YES`, add a Blockers Log row, write `BLOCKED.md`.
2. Update the Human Action Queue with what's needed. Do not fabricate a value to proceed.

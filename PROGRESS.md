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
| Current checkpoint | **CP-0 — Setup & prerequisites** |
| Current ticket | `0.2 Dev environment` (next up, after CP-0 approval) |
| Build gate | 🟢 GREEN (`scripts/check.sh`) |
| Blocked? | No |
| Waiting on human? | **YES — bring up Docker infra + approve CP-0 (see Human Action Queue)** |
| Repo | https://github.com/edos-dws/edos (`main` pushed) |
| Last updated | 2026-07-22 (repo pushed to GitHub) |

---

## Human Action Queue  ⟵ what needs YOU right now

- [x] ~~Create GitHub repo~~ — done: https://github.com/edos-dws/edos (pushed over SSH).
- [ ] Bring up infra: `cp .env.example .env && docker compose up -d` — then confirm Postgres:5432 + Redis:6379 reachable.
- [ ] Confirm the git-as-gate flow (CP-branch → PR → your review/merge).
- [ ] Decide: where the runner runs (this machine vs a VM that stays up).
- [ ] Approve CP-0 once infra is up → runner starts CP-1.

*(Runner: as gates are reached, replace this list with the specific thing the human must validate for that CP.)*

---

## Checkpoint Tracker

Status: ⬜ not started · 🟡 in progress · 🔵 awaiting human review · ✅ approved · 🔴 blocked

| CP | Milestone | Status | Branch / PR | Human validates | Signed off |
|----|-----------|:------:|-------------|-----------------|:----------:|
| CP-0 | Setup, repo, CI, infra | 🟡 | `main` | repo on GH · CI green on a PR · Postgres+Redis reachable · runner can push | ☐ |
| CP-1 | Domain model + persistence | ⬜ | — | schemas capture intent; decision versioning immutable; graph weights | ☐ |
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
| 0.2 Dev environment | ⬜ | — | pyproject installs; pytest/ruff green |
| 0.3 CI-equivalent check script | ✅ | `0c1b3c1` | `scripts/check.sh` + Actions CI |
| 1.1 Decision Pydantic model | ⬜ | — | bound to `decision.schema.json` |
| 1.2 ContextPackage model | ⬜ | — | bound to `context_package.schema.json` |
| 1.3 Core entities + graph edges | ⬜ | — | Ch 3 |
| 2.1 SQLAlchemy models + migrations | ⬜ | — | immutable/versioned decisions |
| 2.2 Decision Graph edges | ⬜ | — | traversal + weights |
| 2.3 pgvector document_chunks | ⬜ | — | embeddings |
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

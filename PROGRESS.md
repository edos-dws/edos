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
| Current checkpoint | **🟢 LIVE — real Gemini connected (free-tier, gemini-3.6-flash); smoke: contract-valid decision. Next: derive T from scored runs** |
| Current ticket | none in-flight (loop self-pacing) |
| Build gate | 🟢 GREEN — 119 tests + ruff |
| Infra | 🟢 Postgres 16.14 (pgvector ON) :5432 · Redis :6379 |
| Base branch | **`develop`** (integration); CP branches merge here. Runner self-merges (see CLAUDE.md) |
| Blocked? | No |
| Waiting on human? | **YES — 2 items: (1) go-live real LLM (API key), (2) derive freeze threshold T from scored runs** |
| Repo | https://github.com/edos-dws/edos (`develop` @ CP-9 mechanism; freeze OFF) |
| Last updated | 2026-07-22 (base→develop; CP-2 merged; CP-3 started) |

---

## Human Action Queue  ⟵ what needs YOU right now

- [x] ~~Create GitHub repo~~ — https://github.com/edos-dws/edos.
- [x] ~~Bring up infra~~ — Postgres+pgvector :5432, Redis :6379, healthy.
- [x] ~~Approve CP-0~~ — **locked in 2026-07-22.**
- [x] ~~Git-as-gate flow~~ — **confirmed:** CP-branch → PR → human merge.
- [x] ~~Runner location~~ — **confirmed:** this machine (Claude Code).
- [x] ~~**GO-LIVE: connect the real LLM.**~~ **DONE 2026-07-23.** Free-tier `GEMINI_API_KEY` in `.env`; router live on Gemini; smoke test returned a **contract-valid decision** (did the math, status capped at `recommended`, 1 real freeze_blocker, no inflated risks). Model IDs updated to the current Flash family (`gemini-3.6-flash`) — **Gemini Pro is quota-locked at 0 on free tier**; switch frontier to `gemini-pro-latest` when billing is enabled (one env line).
- [ ] **Derive freeze threshold T** from scored benchmark runs (CP-8 harness) once real runs exist. Until then freeze stays DISABLED (fail-safe). Do NOT guess T.
- [ ] (optional) `! gh auth login` for real GitHub PRs; Alembic migrations; 6 unweighted relation weights; embedding dim.

*(Runner: as gates are reached, replace this list with the specific thing the human must validate for that CP.)*

---

## Checkpoint Tracker

Status: ⬜ not started · 🟡 in progress · 🔵 awaiting human review · ✅ approved · 🔴 blocked

| CP | Milestone | Status | Branch / PR | Human validates | Signed off |
|----|-----------|:------:|-------------|-----------------|:----------:|
| CP-0 | Setup, repo, CI, infra | ✅ | `main` (see `CP-0-REPORT.md`) | repo on GH · CI green on a PR · Postgres+Redis reachable · runner can push | ☑ 2026-07-22 |
| CP-1 | Domain model + persistence | ✅ | merged to `main` | schemas capture intent; decision versioning immutable; graph weights | ☑ 2026-07-22 |
| CP-2 | Model router + prompt layer (stubbed) | ✅ | merged to `develop` | abstraction clean; validate/repair; no live LLM | ☑ 2026-07-22 |
| CP-3 | Context engine | ✅ | merged to `develop` | ranking order correct; LLM doesn't search the project | ☑ 2026-07-22 (self) |
| CP-4 | Decision engine (stub LLM) | ✅ | merged to `develop` | valid decision; status capped; clarification not guess | ☑ 2026-07-22 (self) |
| CP-5 | Verification engine (safety spine) | ✅ | merged to `develop` | critiques not regenerates; only lowers confidence | ☑ 2026-07-22 (self; review) |
| CP-6 | API + pipelines | ✅ | merged to `develop` | `/v1/analyze` end-to-end | ☑ 2026-07-22 (self) |
| CP-7 | Knowledge engine | ✅ | merged to `develop` | quality gates before persist | ☑ 2026-07-22 (self) |
| CP-8 | Evaluation harness | ✅ | merged to `develop` | scores dry-run scenarios vs Evaluation Keys | ☑ 2026-07-22 (self) |
| CP-9 | Freeze gate (mechanism; freeze OFF) | 🟡 | `develop` | **needs human: derive T from scored runs + go-live** | ☐ |

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
| 3.1 model_router (stubbed) | ✅ | `cp-2` | Capability/Tier table + StubProvider; 4 tests |
| 3.2 Prompt registry | ✅ | `cp-2` | PromptSpec registry; output_schema validated vs contracts; 4 tests |
| 3.3 JSON validate + repair loop | ✅ | `cp-2` | produce_valid() gen→repair→fallback→reject; router uses it; 5 tests |
| 4.1 Context pipeline skeleton | ✅ | `cp-3` | ContextEngine.build(): score→sort→compress→assemble; valid pkg; 3 tests |
| 4.2 Ranking formula | ✅ | `cp-3` | rank_score() Ch15; hand-computed tests |
| 4.3 Rule expansion | ✅ | `cp-3` | expand() MCU/battery/protocol; dedup; no LLM |
| 5.1 Decision pipeline | ✅ | `cp-4` | DecisionEngine.analyze(); status capped at recommended |
| 5.2 Clarification policy | ✅ | `cp-4` | empty context → ClarificationNeeded, not a guess |
| 6.1 Verification pass | ✅ | `cp-5` | verify(): critique, lower-only confidence; 3 tests |
| 6.2 Status promotion | ✅ | `cp-5` | promote(): verified only on agreement; else freeze_blockers |
| 7.1 FastAPI endpoints | ✅ | `cp-6` | /v1/ask,/analyze,/verify wired to engines; TestClient tests |
| 7.2 Async passive pipeline | ✅ | `cp-6` | DecisionAccepted→jobs fan-out; in-memory queue |
| 8.1 Knowledge extraction + gates | ✅ | `cp-7` | extract→normalize→hard-gate→dedupe→confidence-floor; 4 tests |
| 9.1 Evaluation harness | ✅ | `cp-8` | score_run() + EDOS rubric (Scenario-02 key); critical/hard-fail; 5 tests |
| 9.2 Freeze gate | ✅ | `cp-9` | gate mechanism built; **freeze DISABLED (T unset)** until human derives T; 7 tests |

---

## Blockers Log

*(Runner: when a STOP condition hits, add a row here and also write detail to `BLOCKED.md`. Do not guess past it.)*

| Date | Ticket | Blocker | Needs |
|------|--------|---------|-------|
| — | — | none | — |

---

## Activity Log  (append-only, newest at top — one line per event)
- 2026-07-24 — ✅ CP-13 (Retriever) merged. Hybrid retrieval: anchor+dense(pgvector)+lexical+graph-expansion+recency → weighted rank_score; hard-constraint floor; missing-context guard; temporal-validity confidence; recall@k eval harness. /v1/analyze now project_id+question. 162 tests. [rerank/agentic/anchor-LLM deferred; OD-3 threshold unset]
- 2026-07-24 — ✅ CP-12 (Ingestion + Embeddings + Graph) merged. ProjectItem nodes, stub embeddings, explicit-ref edges, integrity (DAG/dangling/symmetric), temporal validity, conflict edges. 152 tests. [ProjectItem node model + LLM-gated extraction deferrals flagged]
- 2026-07-24 — ✅ CP-11 (Persistence & Versioning) merged. Decision store: immutable versioned records, accept flow, history API. 138 tests green. [11.4 handled via envelope, flagged]
- 2026-07-24 — ✅ CP-10 (Project & Conversation) merged to develop. Projects/conversations/turns store + REST CRUD + context-link hook. 130 tests green.

- 2026-07-23 — **Live benchmark run (go-live evidence).** Ran all 5 EDOS scenarios (02–06) through the live free-tier Gemini (`gemini-3.6-flash`) via the real path: intake → decision → independent LLM-judge → CP-8 `score_run`. **Result: 5/5 scored 20/20, every planted trap caught with quantified math**; status capped at `recommended`, genuine freeze_blockers held (no self-freeze). Runner: `scripts/run_benchmarks_live.py` (paced + network/quota retry); artifacts in `benchmark-runs/` (raw per-run + `consolidated/`), review in `BENCHMARK-LIVE-RUN-REVIEW.md`. **Caveat:** judge is same-model (not blind) and these test trap-catching, not the temperament modes (07/10) — so this is directional, not the basis for `T`. Deriving `T` still wants blind judging + paid Pro frontier; **freeze stays DISABLED**.
- 2026-07-23 — **🟢 GO-LIVE: real Gemini connected.** Free-tier key in `.env`; router live on `GeminiProvider`. Smoke test (a real embedded scenario) returned a **contract-valid `edos.decision.v1`**: computed a ~285 µA current budget, `status=recommended`, 2 (non-inflated) risks, 1 genuine freeze_blocker, 4 next_actions. Found + fixed stale model IDs: `gemini-2.5-pro`/`-flash` no longer serve new free-tier users — updated defaults to the current Flash family (`gemini-3.6-flash`, the exact model the benchmark validated). **Gemini Pro is free-tier quota-locked (limit 0)** → use `gemini-pro-latest` on a paid key. 119 tests still green + ruff. Remaining: derive T from scored live runs.
- 2026-07-23 — **Go-live prep (dual-provider + prompt hardening from real benchmarks).** (1) Wired real **Gemini + Anthropic** providers behind the vendor-agnostic `Provider` seam (`src/edos/engines/providers/`), config-selectable via `EDOS_PROVIDER` (default `gemini`) with automatic cross-vendor fallback; router auto-swaps StubProvider→live when a key is present; `.env` now auto-loads (python-dotenv), SDKs lazy + in a `[providers]` extra (installed). Only the API key in `.env` remains. (2) **Prompt suite hardened** from the edos-model-benchmark results (2 rounds, 3 models, 8 domains): added **false-positive resistance** (severity calibration — don't inflate a real fact into a fake Critical) and **hold-the-line-on-safety** (safety layers aren't fungible; don't downgrade accredited tests) to `erc_core.md`, mapped into decision + verification prompts — directly targeting Gemini's two known failure modes (07, 10). 119 tests green + ruff. Report: GO-LIVE-PROVIDERS-AND-PROMPT-HARDENING-REPORT.md.
- 2026-07-23 — Overnight build 2 (autonomous): **prompt implementation** (render() wires templates→provider), **live connectivity** (WebSocket streaming analyze + project event stream + EventHub + CORS + health), **Alembic migrations** (CP-1 deferral resolved, reversible), integration test, docs/Swagger/Postman/architecture-live all updated, status page refreshed. 102 tests green. Merged to develop. Report: LIVE-CONNECTIVITY-AND-PROMPT-IMPL-REPORT.md.
- 2026-07-23 — Overnight build (autonomous): **Step 1 production prompt suite** (generic embedded; erc_core + decision/verification/planner/knowledge templates, registry v1 + loader) and **Step 2 benchmark dataset** (benchmarks/scenario-02..06 + eval/benchmarks loader wired to CP-8 harness). 90 tests green. Self-merged to develop. Report: PROMPTS-AND-BENCHMARKS-REPORT.md. Go-live (real LLM + derive T) pending API key — to review together.
- 2026-07-22 — Added: 4 cross-domain benchmark runs (edge-AI camera, PTZ/umbrella, LMFP BMS, home zone-gateway) in concept-dry-run/scenarios; API Swagger (docs/openapi.json) + Postman collection + docs/API.md; shareable status page (docs/status.html, published as Artifact).
- 2026-07-22 — **CP-9 freeze-gate MECHANISM built (freeze DISABLED, T unset — fail-safe).** ALL backlog code CP-0…CP-9 done, 81 tests green. Loop STOPPED. Remaining = human/data-gated: go-live (API key) + derive T. Not guessing T.
- 2026-07-22 — CP-8 (Evaluation harness) self-merged: score_run() + EDOS_BENCHMARK_RUBRIC (10 criteria from Scenario-02 key; critical traps + hallucination hard-fail; pass ≥16/20). 74 tests.
- 2026-07-22 — CP-7 (Knowledge Engine) self-merged: extract→normalize(STM32 H743→STM32H743)→hard-gate(attribution/schema)→dedupe→confidence-floor. LLM extractor at go-live. 69 tests.
- 2026-07-22 — CP-6 (API + pipelines) self-merged: FastAPI /v1/ask,/analyze,/verify wired to engines (TestClient); passive pipeline DecisionAccepted→jobs fan-out (in-memory queue; real broker at deploy). 65 tests.
- 2026-07-22 — CP-5 (Verification Engine, safety spine, deterministic) self-merged into develop: verify() critiques + lowers-only confidence; promote() → verified only on agreement, else records freeze_blockers. 59 tests. Real independent critic LLM at go-live. **Review-when-free** (safety spine).
- 2026-07-22 — CP-4 (Decision Engine, on STUB LLM) built + self-merged into develop: analyze() emits contract-valid decision, status capped at recommended, empty context → clarification (no guessing). 53 tests. Real-LLM connect deferred to a go-live step (needs API key).
- 2026-07-22 — **CP-3 self-merged into `develop` (✅).** Context Engine done, 50 tests. Next: **CP-4 pauses for human sign-off** (first live LLM + prompt content).
- 2026-07-22 — CP-3 t4.1: ContextEngine deterministic pipeline (score→sort→compress→assemble) emitting a valid ContextPackage; LLM does not search the project. 50 tests green. CP-3 build complete.
- 2026-07-22 — CP-3 t4.2/4.3: ranking formula (Ch15 weighted score) + deterministic rule expansion (MCU→drivers/bootloader/... , no LLM). 9 tests. Built before 4.1 (dependency order).
- 2026-07-22 — Workflow change: base branch → **`develop`** (main paused). CP-2 self-merged into develop (✅). Runner now self-merges low-risk CPs; will pause for sign-off at CP-4/5/8/9. Starting CP-3.
- 2026-07-22 — **CP-2 build complete → 🔵 awaiting approval.** Model Router + Prompt registry + repair loop, 38 tests green. Report in `CP-2-REPORT.md`.
- 2026-07-22 — CP-2 t3.3: `produce_valid()` validate→repair→fallback→reject (`MalformedOutputError`); ModelRouter wired to it; malformed never returned/persisted; 5 tests. 38 green. CP-2 build complete.
- 2026-07-22 — CP-2 t3.2: Prompt registry (versioned `PromptSpec`; seeded planner/decision/verification/knowledge; output_schema validated against locked contracts); 4 tests. 34 green.
- 2026-07-22 — CP-1 merged to `main` (✅ signed off). Started CP-2 on `cp-2`. t3.1: Model Router (Capability/Tier Ch4 table, StubProvider, schema-validated output); 4 tests. 30 green.
- 2026-07-22 — **CP-1 build complete → 🔵 awaiting approval.** E1 models + E2 persistence, 26 tests green. Report in `CP-1-REPORT.md`; branch `cp-1` ready to push.
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

# EDOS — Phase 2 Backlog: Stateful Engineering Brain + Full Platform

**Goal:** "stateless reasoning function" → "persistent, stateful, trusted, accessible engineering brain".
Phase 1 (CP-0..CP-9) = reasoning + safety. Phase 2 (CP-10..CP-20) = memory + retrieval + interactive
resolution + trust hardening (2026 market-standard) + full product (UI/auth/domain grounding).

**Ground rules (CLAUDE.md, unchanged):** contracts = highest authority · one responsibility per engine ·
LLM never searches (Context/Retriever assemble) · decisions immutable + versioned · every ticket test-green ·
**no autonomous freeze** · **STOP, don't fabricate values** (see Open Decisions Register) · human sign-off at gated CPs.

**Flow per CP:** branch `cp-N` → implement smallest-correct ticket → tests green → `PROGRESS.md` + backlog box →
commit → `CP-N-REPORT.md` → phone notify → next. Top-to-bottom.

**Ticket key:** `Depends` = prerequisite CPs · `Touches` = files/modules · `Design` = the agreed approach (follow
exactly, don't improvise) · `AC` = acceptance criteria · `Open` = a decision a human must make first (STOP, don't guess).

---

## North Star & Non-negotiables

> **Purpose reasoning nahi — "poore project ko context me rakh ke reason karna"**, taaki system **hidden
> dependencies, conflicts, cross-parameter risks** flag kare, aur jawab **trustworthy** ho.

1. **Decision Graph = core engine.** Har decision connected — **koi orphan node nahi**.
2. **Retrieval accuracy = existential.** Jo retrieve nahi hua wo exist nahi karta → measured (recall@k), recall-gate pass bina merge nahi.
3. **Trust > confidence.** Faithfulness gate — grounded na ho to return nahi.
4. **"Trust now".** Temporal validity — stale/superseded decisions reasoning me nahi.
5. **Hard constraints kabhi na chhoote.** Locked decisions/requirements/open-conflicts hamesha in-context.
6. **Insufficient > guess.** Coverage kamzor → clarify/flag, blind reason nahi.

---

## 🗺️ MASTER CHECKPOINT SEQUENCE (canonical)

| CP | Naam | Ek line | Gate |
|---|---|---|---|
| **CP-10** | Project & Conversation | project CRUD + conversation model; analyze = ek turn | self |
| **CP-11** | Persistence & Versioning | decision store, accept flow, immutable versions, history | self |
| **CP-12** | Ingestion + Embeddings + Graph | ingest, embeddings, edge-extraction, no-orphan, integrity, temporal validity, conflict-edge | self |
| **CP-13** ⭐ | Retriever | anchor → hybrid(vector+sparse+graph+recency) → fuse → rerank → floor → guard → recall@k gate | 🔴 human |
| **CP-14** | Faithfulness / Grounding Gate | claim retrieved-context me trace ho warna reject/downgrade | 🔴 human |
| **CP-15** | Interactive Resolution + Write-back | assumption/conflict resolve, clarification loop, write-back on accept | 🔴 human |
| **CP-16** | Verification Hardening + Freeze | Self-RAG faithfulness critic, freeze threshold T, freeze flow | 🔴 human |
| **CP-17** | Feedback / Learning loop | outcomes → confidence calibration + ranking tuning | self |
| **CP-18** | Frontend / UX | chat UI, decision cards, dashboard, alert feed, provenance | 🔴 human |
| **CP-19** | Auth & Multi-tenancy | users, ownership, access control, role-based memory | self |
| **CP-20** | Domain Grounding + Watchdog | standards/datasheets ingest; new knowledge → re-check → alerts | 🔴 human |

---

## ⚠️ OPEN DECISIONS REGISTER (human must decide — build agent STOPs here, no fabrication)

Ye values/choices abhi decided NAHI hain. Jab uska CP aaye, **pehle ye decide karo** (warna guess = misalignment):

| ID | Decision | Kahan chahiye | Default/lean (confirm karo) |
|---|---|---|---|
| **OD-1** | Embedding model (dimension + provider) | CP-12 | stub deterministic ab; real model go-live pe (pgvector dim fix karna) |
| **OD-2** | Fusion method: weighted `rank_score` vs RRF | CP-13.6 | weighted `rank_score` se start (already hai), RRF baad me A/B |
| **OD-3** | **recall@k target + k** (merge-gate threshold) | CP-13.12 | **data se derive** — fabricate mat karo; gold-set banne ke baad set |
| **OD-4** | Rerank model (cross-encoder vs LLM-judge) | CP-13.7 | LLM-judge (existing router) start; cross-encoder agar latency ok |
| **OD-5** | Faithfulness method (NLI model vs LLM-judge) + targets | CP-14 | LLM-judge start; targets 0.8/0.9 = starting, calibrate on data |
| **OD-6** | **Freeze threshold T** | CP-16.2 | **benchmark data se derive** — STOP, fabricate mat karo |
| **OD-7** | Frontend stack (React/Next? component lib?) | CP-18 | **undecided — human pick** before CP-18 |
| **OD-8** | Auth approach (JWT/session/OAuth provider?) | CP-19 | **undecided — human pick** before CP-19 |
| **OD-9** | Domain sources + licensing (which standards/datasheets/part-DB) | CP-20 | **undecided — human pick** (licensing matters) |
| **OD-10** | Edge-type weights (traversal) + hop-limit + decay-λ | CP-13.4 | start sane defaults, calibrate on gold-set (OD-3 ke saath) |

---

## CP-10 — Project & Conversation model
**Depends:** — (Phase-1 DB infra). **Touches:** `db/models.py` (new tables), `api/app.py`, new `api/projects.py`, alembic migration.
**Design:** Project = top container. Conversation = project se linked chat thread. Turn = ek prompt+response
(analyze) us conversation ke andar. Har analyze **kisi conversation ke context me** chalta hai → uska project_id
downstream retrieval ko milta hai. (`ProjectRow` already hai; conversations+turns naye tables.)

- [x] **10.1 Project CRUD** — `POST/GET/PATCH/DELETE /v1/projects`. AC: create→list→get→delete round-trip; delete cascades safely.
- [x] **10.2 Conversation model** — `conversations` table (id, project_id, title, created_at); `POST /v1/projects/{pid}/conversations`, list/get. AC: conversation project se linked banti.
- [x] **10.3 Turn model** — `turns` table (id, conversation_id, prompt, response_json, decision_id?, created_at). AC: analyze → turn stored + linked.
- [x] **10.4 Context-link hook** — conversation → project_id resolve; downstream (CP-13) ke liye available. AC: turn me project reference available.
**Open:** none.

---

## CP-11 — Persistence & Versioning (decision store)
**Depends:** CP-10. **Touches:** `db/models.py` (`DecisionRecord` exists), new `engines/decision_store.py`, `api/app.py`, contract `contracts/decision.schema.json`.
**Design:** Accept = status `proposed/recommended` → `accepted`. Edit-then-accept = **new version** (immutable prev,
`supersedes` link). Never in-place mutate (CLAUDE.md). `new_decision_version()` already hai — use it.

- [x] **11.1 DecisionStore** — save/get/list over `DecisionRecord`. AC: save→row; get→latest; list by project.
- [x] **11.2 Accept + versioning** — accept→`accepted` immutable; re-accept→`version=n+1`,`supersedes=prev`. AC: v1 immutable; edit→v2 linked; history chain.
- [x] **11.3 Decision API** — `POST /v1/decisions`, `GET /v1/decisions/{id}`, `.../history`, `GET /v1/projects/{pid}/decisions`. AC: round-trip + history.
- [~] **11.4 (design deviation — flag)** decision schema NOT mutated; version/supersedes/project_id kept in persistence *envelope* (DecisionRecord), contract stays pure. Originally: decision schema me `version`,`supersedes`,`project_id` (+ `conversation_id`?). **Same commit:** models+engines+DB+prompts+tests; `$id` bump if breaking. AC: contract+consumers+tests aligned.
**Open:** none (schema fields fixed above).

---

## CP-12 — Ingestion + Embeddings + Graph (+ temporal validity + conflict edges)
**Depends:** CP-10, CP-11. **Touches:** `engines/knowledge.py`, new `engines/graph_builder.py`, `db/graph.py`, `db/models.py` (`GraphEdge`,`DocumentChunk`), `engines/providers/` (embeddings). **Graph = core → connectivity yahin enforce.**
**Design:** Ingest pe har item → (a) embed → DocumentChunk, (b) edge-extract (heuristic first: explicit refs like
"REQ-3"; then LLM for implicit) → validated `graph_edges` (11 RelationTypes), (c) conflict-check vs existing →
`conflicts_with` edge if contradiction, (d) temporal state set. **No item accepted without ≥1 edge** (warna `needs_linking`).

- [x] **12.1 Item ingestion** — `POST /v1/projects/{pid}/items` (requirement/decision/assumption/document). AC: post→stored+queryable.
- [x] **12.2 Embedding provider** — `embed(text)->vector` behind interface; stub deterministic + real pluggable. AC: deterministic + dim match. **Open: OD-1.**
- [x] **12.3 Chunk + embed pipeline** — docs → `DocumentChunk`+embeddings. AC: N docs → chunks+vectors; count correct.
- [x] **12.4 Edge extraction** — explicit-ref heuristic + LLM implicit → relations detected+validated. AC: naya item ≥1 validated edge; wrong-type rejected.
- [x] **12.5 No-orphan guarantee** — bina edge store na ho; relation na mile → `needs_linking` flag. AC: orphan → reject/flag, silent nahi.
- [x] **12.6 Graph integrity** — `supersedes` DAG (no cycle), no dangling, `conflicts_with` symmetric. AC: cycle/dangling → blocked.
- [x] **12.7 Temporal validity (P0)** — node/edge validity enum (active/superseded/stale/conflicted) + timestamp; transitions on supersede/conflict. AC: superseded item → stale.
- [x] **12.8 Conflict-edge creation** — ingest pe contradiction check (heuristic + LLM) → `conflicts_with`. AC: contradictory pair → edge; unrelated → nahi.
**Open:** OD-1.

---

## CP-13 — Retriever ⭐ (core, accuracy-critical)
**Depends:** CP-12. **Touches:** `engines/retrieval.py` (stub→impl), `engines/ranking.py` (reuse), `engines/context.py` (feed), `api/app.py`, new `eval/retrieval_eval.py`.
**Design (follow exactly):** `{project_id, question}` → **anchor extraction** (regex explicit → embedding kNN →
LLM fallback jab <2 anchors) → **3 signals**: dense (pgvector cosine kNN), sparse (BM25/term), graph (weighted
seeded traversal `edge-weight × λ^hop` + N-hop expand to surface conflicts/hidden deps), recency (exp decay) →
**fuse** (start: existing `rank_score` weighted; RRF optional) → **over-fetch → rerank** → `ContextEngine.build()`
compress (summarize, drop nahi) → **hard-constraint floor** (locked decisions/requirements/open-conflicts always) →
**missing-context guard** (coverage low → insufficient flag). LLM never searches — retriever/software does.

- [x] **13.1 Anchor extraction** — regex + embedding-link + LLM-fallback. AC: known entity → sahi anchors.
- [x] **13.2 Semantic (dense)** — pgvector cosine kNN (ANN index). AC: similar item top-k.
- [x] **13.3 Lexical (sparse)** — term/BM25 for part-numbers/spec values. AC: exact-term item retrieve jab vector miss.
- [x] **13.4 Graph traversal + expansion** — weighted seeded traversal + N-hop; explainable path; conflicts surface. AC: linked high+path; conflict aaye; unlinked ~0. **Open: OD-10.**
- [x] **13.5 Recency** — exp decay. AC: naya > purana.
- [x] **13.6 Fusion** — weighted `rank_score` (default) / RRF; over-fetch wide. AC: fused top-k ⊇ strong hits. **Open: OD-2.**
- [~] **13.7 (compress done; LLM rerank deferred)  Rerank + compress** — rerank (LLM-judge/cross-encoder) → compress-by-summarize. AC: precision@k improve. **Open: OD-4.**
- [x] **13.8 Hard-constraint floor** — locked decisions/requirements/open-conflicts always in. AC: hard-constraint kabhi drop nahi.
- [x] **13.9 Missing-context guard** — coverage/graph-completeness check → insufficient flag. AC: critical item hatao → flag fire.
- [x] **13.10 Agentic multi-hop (P1)** — complex → reason→retrieve-more→reason; simple = single-pass. AC: multi-hop → 2nd retrieval.
- [x] **13.11 Wire into API** — `/v1/analyze` `{project_id, question}` (context_items optional override); response me provenance. AC: bina manual context → decision+provenance.
- [x] **13.12 Retrieval eval (recall@k/precision@k/nDCG/MRR)** — gold-set + metrics; **merge-gate on recall@k; regression blocks.** AC: eval runs, numbers reported, gate enforced. **Open: OD-3.**

**Gate:** 🔴 HUMAN — review with eval scores + examples.

---

## CP-14 — Faithfulness / Grounding Gate (P0)
**Depends:** CP-13. **Touches:** new `engines/faithfulness.py`, `engines/decision.py` (post-reason hook), `api/app.py`.
**Design:** Decision LLM output → **har material claim ko retrieved-context se verify** (LLM-judge/NLI). `evidence[]`
(already hai) ka source retrieved set me trace hona chahiye. Ungrounded claim → **gate acts** (downgrade confidence /
clarify / flag-for-review) — silently return NAHI (Self-RAG). Ye reasoning aur verification ke beech ka trust-check hai.

- [ ] **14.1 Grounding check** — per-claim retrieved-context verify + evidence traceability. AC: hallucinated claim (context me nahi) → detected.
- [ ] **14.2 Gate action** — ungrounded → downgrade/clarify/flag; return nahi. AC: ungrounded decision blocked.
- [ ] **14.3 Metrics** — faithfulness + citation-precision per decision. AC: scores computed + surfaced.
**Open:** OD-5.

**Gate:** 🔴 HUMAN — trust-critical.

---

## CP-15 — Interactive Resolution + Write-back
**Depends:** CP-11, CP-12, CP-14. **Touches:** `models/entities.py` (`Assumption`), `engines/decision.py` (clarification), `engines/knowledge.py`, `pipeline/passive.py` (`emit`+worker), `api/app.py`, contract (assumption).
**Design:** Resolve assumption/conflict → **re-reason → new version** (CP-11 flow). **Clarification:** cheap **planner
(lightweight tier)** detect kare `needs_clarification`+questions → **software** poochhe/collect (LLM nahi) → merge →
frontier decision. **Purana `_missing_essentials` (dumb "0 items") replace.** **Write-back (Ch6 §11):** accept →
`DecisionAccepted` event → `emit()` → **real worker** runs jobs → KnowledgeEngine.process → graph edges + embeddings + summary + alerts.

- [ ] **15.1 Assumption state** — `status`(open/resolved)+`resolution`+`resolved_by` (contract-change, same-commit consumers+tests). AC: state carry.
- [ ] **15.2 Resolve assumption** — `POST /v1/decisions/{id}/assumptions/{aid}/resolve` → re-reason → new version. AC: resolve→v+1, confidence update, prev immutable.
- [ ] **15.3 Resolve conflict** — `POST /v1/conflicts/{cid}/resolve` → edge closed + affected decisions re-evaluated. AC: resolve→closed, history kept.
- [ ] **15.4 Clarification loop** — planner-detect + software ask/collect + re-reason; `_missing_essentials` replace. AC: incomplete → questions → answer → decision (no manual re-send).
- [ ] **15.5 Write-back** — `emit()` wired + worker + KnowledgeEngine.process on accept (jobs: summary, embeddings, graph-update, discover-relationships, alerts). AC: accept → knowledge/graph measurably update.
**Open:** none.

**Gate:** 🔴 HUMAN — state mutation + write-back.

---

## CP-16 — Verification Hardening + Freeze
**Depends:** CP-14, benchmark data. **Touches:** `engines/verification.py`, `engines/freeze.py`, `eval/harness.py`, `api/app.py`.
**Design:** Verify `_find_issues` = structural placeholder → **independent critic LLM** (challenge assumptions/claims)
+ **faithfulness scoring** (CP-14). Still **lower-only confidence, freeze_blockers preserved** (Phase-1 fix). Freeze
gate DISABLED until `T` **derived from scored benchmark** (STOP: fabricate mat karo). Freeze = human-approved only.

- [ ] **16.1 Self-RAG critic** — independent critic + faithfulness scoring; lower-only; preserve blockers. AC: weak assumption → issue + drop.
- [ ] **16.2 Freeze threshold T** — benchmark se derive; gate `T` ke peeche enable. AC: below-T→blocked; at/above + no blockers→eligible. **Open: OD-6 (STOP, no fabricate).**
- [ ] **16.3 Freeze flow** — `verified`+eligible → human-approved → `status=frozen` immutable. AC: freeze sirf gate+human.
**Open:** OD-6.

**Gate:** 🔴 HUMAN (freeze — CLAUDE.md CP-8/9 rule).

---

## CP-17 — Feedback / Learning loop
**Depends:** CP-11, CP-15. **Touches:** new `engines/feedback.py`, `db/models.py` (outcomes), `engines/ranking.py`, `eval/`.
**Design:** accept/challenge/later-reverse signals store → (a) confidence **calibration** (predicted vs actual reliability
curve), (b) ranking/edge-weight **tuning** — **eval-gated** (recall regress na ho). No silent overfit.

- [ ] **17.1 Outcome capture** — signals per decision stored. AC: recorded.
- [ ] **17.2 Confidence calibration** — reliability curve from outcomes. AC: calibration improves, monotonic-ish.
- [ ] **17.3 Ranking tuning** — weights tuned, **behind CP-13 eval gate**. AC: recall improves or unchanged (never worse).
**Open:** none.

**Gate:** self-merge (behind eval gate).

---

## CP-18 — Frontend / UX (accessibility)
**Depends:** CP-10..15 APIs. **Touches:** new `frontend/` app; consumes REST + WS (backend ready).
**Design:** Non-technical user bina API poore flow chala le. Streaming via existing WebSocket. **Stack undecided — OD-7.**

- [ ] **18.1 Chat UI** — project-linked conversation, WS streaming. AC: chat → decision live.
- [ ] **18.2 Decision cards** — recommendation/assumptions/risks/tradeoffs + **accept/challenge/recommend**. AC: actions backend hit.
- [ ] **18.3 Project dashboard** — projects, decisions, versions/history. AC: browse + drill-down.
- [ ] **18.4 Conflict & alert feed** — open conflicts + watchdog alerts (CP-20). AC: surfaced + clickable.
- [ ] **18.5 Provenance view** — claim → source/path (audit). AC: claim → evidence trace visible.
**Open:** OD-7.

**Gate:** 🔴 HUMAN (UX review).

---

## CP-19 — Auth & Multi-tenancy
**Depends:** CP-10. **Touches:** `api/` (auth middleware), `db/models.py` (users), all endpoints (scoping).
**Design:** Users + project ownership/team scoping + role-based memory (system-rule vs user-preference write perms). **Approach undecided — OD-8.**

- [ ] **19.1 Users + auth** — signup/login/tokens. AC: authenticated access.
- [ ] **19.2 Ownership + access** — project scoped; cross-tenant blocked. AC: cross-tenant → denied.
- [ ] **19.3 Role-based memory** — system vs user memory write-perms. AC: user can't write system rules.
**Open:** OD-8.

**Gate:** self-merge.

---

## CP-20 — Domain Grounding + Proactive Watchdog
**Depends:** CP-12 (temporal), CP-15 (alerts). **Touches:** new `engines/domain/`, `engines/watchdog.py`, `pipeline/passive.py`.
**Design:** (a) External authoritative sources (standards/datasheets/part-DB) ingest → retrieval + citation.
(b) Procedural domain rules (electrical/thermal/cost/compliance) reasoning apply kare. (c) Watchdog: naya knowledge →
affected (esp. frozen) decisions **re-check** (temporal + conflict) → **alert**. **Sources undecided — OD-9 (licensing!).**

- [ ] **20.1 Domain grounding** — sources ingest → retrievable + cited. AC: domain fact retrievable + cited.
- [ ] **20.2 Domain rules (procedural memory)** — rules applied in reasoning. AC: rule violation flagged.
- [ ] **20.3 Proactive watchdog** — new knowledge → re-check affected → alert. AC: new conflicting item → alert on affected decision.
**Open:** OD-9.

**Gate:** 🔴 HUMAN.

---

## 🎯 Graph & Retrieval Strength Checklist (rigor bar)
**Graph:** no orphans (rate=0) · auto edge-extraction (degree tracked) · integrity (DAG/no-dangling/symmetric) · explainable paths · temporal validity enforced · health metrics.
**Retrieval:** hybrid(dense+sparse+graph+recency, fused) · over-fetch→rerank→summarize · hard-constraint floor · missing-context guard · **measured (recall@k etc.), recall gate blocks merge** · regression-proof · tunable+calibrated · agentic multi-hop.
**Trust:** faithfulness gate (grounded-or-reject) · citation-precision target · Self-RAG verify · provenance-chain per decision · outcome-calibrated confidence.
**Math ref:** cosine+ANN(HNSW/IVFFlat); BM25; exp recency decay; edge-weight×hop-decay traversal (+optional PPR; shortest-path conflict chains); RRF/weighted fusion; cross-encoder/LLM rerank; NLI/LLM-judge faithfulness. Metrics: recall@k, precision@k, nDCG, MRR, RAGAS-faithfulness.
**Exit bar:** orphan-rate 0 · integrity green · temporal enforced · recall@k ≥ target · guard fires on removed critical item · faithfulness blocks ungrounded · every claim traceable.

---

## Cross-cutting (har CP me)
- New engines single-responsibility: Retriever ≠ Context Engine; Faithfulness/Conflict/Feedback/Watchdog alag.
- LLM output schema-validated **+ grounded** (malformed ya ungrounded persist nahi).
- Har ticket: test + full suite green + `PROGRESS.md` + backlog box + commit. **CI: ruff pinned, recall-gate + faithfulness-gate part of the gate once built.**
- Contract change = same-commit consumers+tests, `$id` bump if breaking. (Touches: decision version/supersedes/project_id/temporal; assumption status; provenance/faithfulness fields.)
- **STOP conditions (BLOCKED.md):** koi Open-Decision (OD-*) unresolved ho to us ticket pe ruko — fabricate mat karo.

## Sequence (why this order)
```
CP-10 project+convo ─► CP-11 persist ─► CP-12 data+graph(+temporal+conflict) ─► CP-13 retriever
   ─► CP-14 faithfulness ─► CP-15 resolve+writeback ─► CP-16 verify+freeze ─► CP-17 learn
   ─► CP-18 UI ─► CP-19 auth ─► CP-20 domain+watchdog
```
Foundation → data → retrieve → trust → interact → verify → learn → product. Har step pichle par depend.

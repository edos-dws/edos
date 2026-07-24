# EDOS — Phase 2 Backlog: Stateful Engineering Brain + Full Platform

**Goal:** "stateless reasoning function" → "persistent, stateful, trusted, accessible engineering brain".
Phase 1 (CP-0..CP-9) = reasoning + safety. Phase 2 (CP-10..CP-20) = memory + retrieval + interactive
resolution + trust hardening (2026 market-standard) + full product (UI/auth/domain grounding).

**Ground rules (CLAUDE.md, unchanged):** contracts = highest authority · one responsibility per engine ·
LLM never searches (Context/Retriever assemble) · decisions immutable + versioned · every ticket test-green ·
**no autonomous freeze** · stop for human sign-off at gated checkpoints.

**Flow:** har CP ek branch (`cp-N`) → develop merge → `CP-N-REPORT.md` → phone notify. Top-to-bottom order.

---

## North Star & Non-negotiables

> **Purpose reasoning nahi — "poore project ko context me rakh ke reason karna"**, taaki system **hidden
> dependencies, conflicts, cross-parameter risks** flag kare, aur jawab **trustworthy** ho.

1. **Decision Graph = core engine.** Har decision connected — **koi orphan node nahi**.
2. **Retrieval accuracy = existential.** Jo retrieve nahi hua wo exist nahi karta → measured (recall@k), recall-gate pass bina merge nahi.
3. **Trust > confidence.** Faithfulness gate — grounded na ho to return nahi (silently confident-galat mana hai).
4. **"Trust now".** Temporal validity — stale/superseded decisions reasoning me nahi ghusni chahiye.
5. **Hard constraints kabhi na chhoote.** Locked decisions/requirements/open-conflicts hamesha in-context.
6. **Insufficient > guess.** Coverage kamzor → clarify/flag, blind reason nahi.

---

## 🗺️ MASTER CHECKPOINT SEQUENCE (canonical — yahi follow karo)

| CP | Naam | Ek line | Gate |
|---|---|---|---|
| **CP-10** | Project & Conversation | project CRUD + conversation model (project-linked chat); analyze = ek turn | self |
| **CP-11** | Persistence & Versioning | decision store, accept flow, immutable versions, history API | self |
| **CP-12** | Ingestion + Embeddings + Graph | item ingest, embeddings, edge-extraction, **no-orphan**, integrity, **temporal validity**, **conflict-edge creation** | self |
| **CP-13** ⭐ | Retriever | anchor → hybrid (vector+sparse+graph-expansion+recency) → fuse → rerank → floor → missing-context guard → **recall@k gate** | 🔴 human |
| **CP-14** | Faithfulness / Grounding Gate | har claim retrieved-context me trace ho warna reject/downgrade | 🔴 human |
| **CP-15** | Interactive Resolution + Write-back | assumption/conflict resolve, clarification loop, **knowledge/graph write-back on accept** | 🔴 human |
| **CP-16** | Verification Hardening + Freeze | Self-RAG faithfulness critic, freeze threshold T, freeze flow | 🔴 human |
| **CP-17** | Feedback / Learning loop | accept/challenge/reverse → confidence calibration + ranking tuning | self |
| **CP-18** | Frontend / UX | chat UI, decision cards, project dashboard, conflict/alert feed, provenance, WS streaming | 🔴 human |
| **CP-19** | Auth & Multi-tenancy | users, project ownership, access control, role-based memory | self |
| **CP-20** | Domain Grounding + Proactive Watchdog | standards/datasheets/part-DB ingest; new knowledge → re-check decisions → alerts | 🔴 human |

**Dependency order:** project+conversation → persist → data+graph → retrieve → faithfulness → interactive+write-back
→ verify+freeze → learn → UI → auth → domain+watchdog. Har step pichle par depend.

---

## CP-10 — Project & Conversation model
*Foundation. Bina project+conversation ke "project se chat" aur context-linking possible hi nahi.*

- [ ] **10.1 Project CRUD** — `POST/GET/PATCH/DELETE /v1/projects` (`ProjectRow` already hai). AC: create→list→get→delete round-trip.
- [ ] **10.2 Conversation model** — conversation project se linked; `POST /v1/projects/{pid}/conversations`,
  list/get. AC: project ke andar conversation banti + linked.
- [ ] **10.3 Turn model** — har `analyze` ek conversation-turn (prompt+response) store ho. AC: turn stored + conversation se linked.
- [ ] **10.4 Context auto-link hook** — jab conversation project se linked ho, uska project_id downstream
  retrieval ko available ho (CP-13 use karega). AC: turn me project context reference available.

**Gate:** self-merge. Report + notify.

---

## CP-11 — Persistence & Versioning (decision store)
*Accepted decisions immutable + versioned.*

- [ ] **11.1 DecisionStore** — `DecisionRecord` (+ `new_decision_version()`) pe save/get/list. AC: save→row; get→latest; list by project.
- [ ] **11.2 Accept flow + versioning** — accept → `status=accepted`, immutable; re-accept(edited) → `version=n+1`,
  `supersedes=<prev>`, prev untouched. AC: v1 immutable; edit→v2 linked; history chain retrievable.
- [ ] **11.3 Decision API** — `POST /v1/decisions`, `GET /v1/decisions/{id}`, `.../history`, `GET /v1/projects/{pid}/decisions`. AC: round-trip + history chain.
- [ ] **11.4 Contract** — decision schema me `version`/`supersedes`/`project_id` add karo agar missing
  (contract-change: consumers+tests same commit, `$id` bump if breaking).

**Gate:** self-merge. Report + notify.

---

## CP-12 — Ingestion + Embeddings + Graph (+ temporal validity + conflict edges)
*Retriever ko fetch karne ke liye data + strong connected graph chahiye. Graph = core → connectivity yahin enforce.*

- [ ] **12.1 Item ingestion** — `POST /v1/projects/{pid}/items` (requirement/decision/assumption/document). AC: post→stored+queryable.
- [ ] **12.2 Embedding provider** — `embed(text)->vector`, stub deterministic + real pluggable (interface, jaise model_router). AC: deterministic + dim match.
- [ ] **12.3 Chunk + embed pipeline** — docs → `DocumentChunk` + embeddings. AC: N docs → chunks+vectors; count correct.
- [ ] **12.4 Edge extraction (connectivity)** — naya item pe relations (depends_on/affects/constrains/supersedes/references)
  detect (heuristic+LLM) → `graph_edges`. AC: naya item ≥1 validated edge.
- [ ] **12.5 No-orphan guarantee** — bina edge decision store na ho; relation na mile → `needs_linking` flag (silent orphan nahi). AC: orphan → reject/flag.
- [ ] **12.6 Graph integrity** — `supersedes` DAG (no cycle), no dangling, `conflicts_with` symmetric. AC: cycle/dangling → blocked.
- [ ] **12.7 Temporal validity (P0)** — har node/edge pe validity state (active/superseded/stale/conflicted) + timestamp. AC: superseded item marked stale.
- [ ] **12.8 Conflict-edge creation** — ingest pe naya item existing state se contradiction check → `conflicts_with` edge.
  (Detection yahan graph-time; surfacing/resolution CP-13/CP-15.) AC: contradictory pair → edge; unrelated → nahi.

**Gate:** self-merge. Report + notify.

---

## CP-13 — Retriever ⭐ (core, accuracy-critical)
*project_id + question → poore project ka relevant context KHUD assemble. `retrieval.py` stub implement.*
*Sabse critical CP — retrieval galti = reasoning fail. Har ticket measurable.*

- [ ] **13.1 Anchor extraction** — question se entities/refs → graph seed nodes (regex + embedding-link + LLM-fallback). AC: known entity → sahi anchors.
- [ ] **13.2 Semantic (dense)** — question embed → pgvector cosine kNN (HNSW/IVFFlat). AC: similar item top-k.
- [ ] **13.3 Lexical (sparse)** — keyword/BM25 for exact terms/part-numbers/spec values. AC: exact-term item retrieve jab vector miss kare.
- [ ] **13.4 Graph traversal + expansion** — anchors se weighted seeded traversal (edge-weight × hop-decay `λ^hop`);
  N-hop expand → connected decisions **+ conflicts surface** (core purpose). Explainable path. AC: linked item high+path; conflict aaye; unlinked ~0.
- [ ] **13.5 Recency** — exponential time decay. AC: naya > purana.
- [ ] **13.6 Fusion** — dense+sparse+graph+recency → RRF / calibrated `rank_score`; over-fetch wide. AC: fused top-k ⊇ strong hits.
- [ ] **13.7 Rerank + compress** — cross-encoder/LLM rerank → `ContextEngine.build()` compress (drop nahi to **summarize**). AC: precision@k improve.
- [ ] **13.8 Hard-constraint floor** — locked decisions/requirements/open-conflicts hamesha include. AC: hard-constraint kabhi drop na ho.
- [ ] **13.9 Missing-context guard** — coverage/graph-completeness check; low → "insufficient context" flag. AC: critical item hatao → flag fire.
- [ ] **13.10 Agentic multi-hop (P1)** — complex question pe reason→"X missing"→retrieve-more→reason again; simple = single-pass. AC: multi-hop → 2nd retrieval.
- [ ] **13.11 Wire into API** — `/v1/analyze` `{project_id, question}` le (context_items optional override); Retriever→ContextEngine→DecisionEngine; response me **provenance**. AC: bina manual context → decision+provenance.
- [ ] **13.12 Retrieval eval (recall@k, precision@k, nDCG, MRR)** — gold set + metrics; **merge-gate: recall@k < target → block; regression → block.** AC: eval runs; numbers reported; gate enforced.

**Gate:** 🔴 **HUMAN** — retrieval quality sab par asar. Review with eval scores + examples. Report + notify.

---

## CP-14 — Faithfulness / Grounding Gate (P0)
*Decision return karne se pehle: har material claim retrieved-context se grounded ho, hallucinate nahi.*

- [ ] **14.1 Grounding check** — decision ke har material claim ko retrieved context se verify (LLM-judge/NLI);
  `evidence[]` source retrieved set me trace ho. AC: hallucinated claim (context me nahi) → detected.
- [ ] **14.2 Gate action** — grounded na ho → **return mat karo** → downgrade confidence / clarify / flag-for-review (Self-RAG). AC: ungrounded decision blocked, silently pass nahi.
- [ ] **14.3 Metrics** — faithfulness score + citation-precision per decision; targets (≥0.8 / ≥0.9) tracked. AC: scores computed + surfaced.

**Gate:** 🔴 **HUMAN** — trust-critical. Report + notify.

---

## CP-15 — Interactive Resolution + Write-back
*Engineer resolve kare → re-reason → naya version. Accept → project knowledge update (roadmap Ch6 §11).*

- [ ] **15.1 Assumption state** — `Assumption` me `status`(open/resolved)+`resolution`+`resolved_by` (contract-change). AC: state carry.
- [ ] **15.2 Resolve assumption** — `POST /v1/decisions/{id}/assumptions/{aid}/resolve` → record → re-reason → new version. AC: resolve→v+1, confidence update, prev immutable.
- [ ] **15.3 Resolve conflict** — `POST /v1/conflicts/{cid}/resolve` → edge closed + affected decisions re-evaluated. AC: resolve→closed, history kept.
- [ ] **15.4 Clarification loop** — **planner (cheap tier) detect** kare `needs_clarification`+questions → **software** user se poochhe/collect → merge → decision. (Alag heavy LLM call nahi; dumb `_missing_essentials` replace.) AC: incomplete prompt → questions → answer → decision (no manual re-send).
- [ ] **15.5 Write-back (Ch6 §11)** — accept → `DecisionAccepted` event → KnowledgeEngine.process → graph edges +
  embeddings + summary update + alerts enqueue (`emit()` + real worker). AC: accept → knowledge/graph measurably update.

**Gate:** 🔴 **HUMAN** — state mutation + write-back semantics. Report + notify.

---

## CP-16 — Verification Hardening + Freeze
*Structural-only critic → real independent + faithfulness-aware. Freeze = consequential.*

- [ ] **16.1 Self-RAG critic** — verify `_find_issues` upgrade: independent critic LLM jo assumptions/claims challenge kare
  + **faithfulness scoring** (CP-14 se). Still lower-only confidence, freeze_blockers preserve. AC: weak assumption → issue + drop.
- [ ] **16.2 Freeze threshold T** — scored benchmark runs se `T` derive (STOP: fabricate mat karo — data se). Freeze gate `T` ke peeche enable. AC: below-T → blocked; at/above + no freeze_blockers → eligible.
- [ ] **16.3 Freeze flow** — `verified`+eligible → human-approved freeze → `status=frozen` (immutable final). AC: freeze sirf gate+human; autonomous nahi.

**Gate:** 🔴 **HUMAN** (freeze). Report + notify.

---

## CP-17 — Feedback / Learning loop
*accept/challenge/reverse outcomes → system smart bane. Trace→Reason→Learn→Replay.*

- [ ] **17.1 Outcome capture** — accept/challenge/later-reverse signals per decision store. AC: signals recorded.
- [ ] **17.2 Confidence calibration** — outcomes se confidence calibrate (predicted vs actual-correct). AC: calibration curve improves.
- [ ] **17.3 Ranking tuning** — accepted decisions ke context patterns se rank-weights/edge-weights tune. AC: retrieval recall improves on eval over rounds.

**Gate:** self-merge (behind eval gate). Report + notify.

---

## CP-18 — Frontend / UX (accessibility)
*"Sabke liye" = UI. Non-technical user bina API poore flow chala le.*

- [ ] **18.1 Chat UI** — project-linked conversation, streaming (WS backend ready). AC: chat → decision live.
- [ ] **18.2 Decision cards** — recommendation + assumptions/risks/tradeoffs + **accept / challenge / recommend** actions. AC: actions backend hit karein.
- [ ] **18.3 Project dashboard** — projects, decisions, versions/history. AC: browse + drill-down.
- [ ] **18.4 Conflict & alert feed** — open conflicts + proactive alerts (CP-20). AC: surfaced + clickable.
- [ ] **18.5 Provenance view** — har claim → source/path (audit). AC: claim → evidence trace visible.

**Gate:** 🔴 **HUMAN** (UX review). Report + notify.

---

## CP-19 — Auth & Multi-tenancy
*Multi-user platform.*

- [ ] **19.1 Users + auth** — signup/login, tokens. AC: authenticated access.
- [ ] **19.2 Project ownership + access** — project scoped to owner/team; access control. AC: cross-tenant access blocked.
- [ ] **19.3 Role-based memory** — system-rule memory vs user-preference memory, write-permission segregation. AC: user can't write system rules.

**Gate:** self-merge. Report + notify.

---

## CP-20 — Domain Grounding + Proactive Watchdog
*Vertical depth + "jo tumne poocha nahi wo bhi batao" — differentiators.*

- [ ] **20.1 Domain grounding** — standards (AEC-Q100 etc.)/datasheets/part-DB ingest → retrieval over authoritative external sources. AC: domain fact retrievable + cited.
- [ ] **20.2 Domain rules (procedural memory)** — electrical/thermal/cost/compliance rules that reasoning applies. AC: rule violation flagged.
- [ ] **20.3 Proactive watchdog** — naya knowledge → affected (esp. frozen) decisions re-check (temporal validity + conflict) → **alert**. AC: new conflicting item → alert on affected decision.

**Gate:** 🔴 **HUMAN**. Report + notify.

---

## 🎯 Graph & Retrieval Strength Checklist (rigor bar — "ganit")

**Graph strength**
- [ ] No orphans (orphan-rate=0) · auto edge-extraction (avg-degree tracked) · integrity (DAG, no dangling, symmetric conflicts) · explainable paths · health metrics (orphan-rate/degree/components/cycles) · **temporal validity enforced**.

**Retrieval strength**
- [ ] Hybrid (dense+sparse+graph-expansion+recency, fused) · over-fetch→rerank→compress(summarize) · hard-constraint floor · missing-context guard · **measured (recall@k/precision@k/nDCG/MRR), recall gate blocks merge** · regression-proof · tunable+calibrated · agentic multi-hop for complex.

**Trust**
- [ ] **Faithfulness gate** (grounded-or-reject) · citation-precision target · Self-RAG verify · provenance-chain per decision · confidence calibrated from outcomes.

**The math (reference):** cosine + ANN (HNSW/IVFFlat); BM25; exponential recency decay; edge-weight × hop-decay
traversal (+ optional Personalized PageRank; shortest-path for conflict chains); RRF / calibrated linear fusion;
cross-encoder rerank; NLI/LLM-judge faithfulness. Metrics: recall@k, precision@k, nDCG, MRR; RAGAS faithfulness.

**Phase-2 exit bar:** orphan-rate 0 · integrity green · temporal validity enforced · recall@k ≥ target ·
missing-context guard fires when critical item removed · faithfulness gate blocks ungrounded · every claim traceable.

---

## Cross-cutting (har CP me)
- New engines single-responsibility: Retriever ≠ Context Engine (retriever fetch+signals; context rank+compress);
  Faithfulness gate, Conflict detector, Feedback/calibration — alag concerns.
- Sab LLM output schema-validated **+ grounded** (repair/reject; malformed ya ungrounded persist nahi).
- Har ticket: test added + full suite green + `PROGRESS.md` update + backlog box check + commit.
- Contract change = same-commit consumers+tests, `$id` bump if breaking. (Touches: decision version/supersedes/temporal,
  assumption status, provenance/faithsfulness fields.)

## Sequence (why this order)
```
CP-10 project+convo ─► CP-11 persist ─► CP-12 data+graph(+temporal+conflict) ─► CP-13 retriever
   ─► CP-14 faithfulness ─► CP-15 resolve+writeback ─► CP-16 verify+freeze ─► CP-17 learn
   ─► CP-18 UI ─► CP-19 auth ─► CP-20 domain+watchdog
```
Foundation → data → retrieve → trust → interact → verify → learn → product. Har step pichle par depend.

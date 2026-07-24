# EDOS — Phase 2 Backlog: Stateful Engineering Brain

**Goal:** "stateless reasoning function" → "persistent stateful engineering brain".
Phase 1 (CP-0..CP-9) ne reasoning + safety banaya. Phase 2 (CP-10..CP-15) iske aas-paas ka
**memory + retrieval + interactive resolution** wire karta hai.

**Ground rules (CLAUDE.md se, unchanged):** contracts = highest authority · one responsibility per engine ·
LLM never searches (Context/Retriever assemble karte hain) · decisions immutable + versioned · har ticket ka
test green · **no autonomous freeze** · human gate marked checkpoints pe ruko.

**Order:** top-to-bottom. Har CP ek branch (`cp-N`) → develop me merge → `CP-N-REPORT.md` → phone notify.

---

## North Star & Non-negotiables (Phase 2 ka asli maqsad)

> **Purpose reasoning nahi hai — purpose "poore project ko context me rakh ke reason karna" hai**, taaki
> system **hidden dependencies, conflicts, aur cross-parameter risks flag** kar sake. Isliye:

1. **Decision Graph = core engine.** Har decision doosri decisions/requirements se **connected** honi chahiye.
   **Koi orphan node nahi** — bina edge ke decision store hi nahi honi chahiye.
2. **Retrieval accuracy = existential.** Jo retrieve nahi hua, LLM ko exist hi nahi karta → reasoning silently
   fail. Isliye retrieval ko **maapa** jayega (recall@k), guess nahi. **Recall gate pass kiye bina merge nahi.**
3. **Miss karne se confident-galat behtar nahi.** Agar coverage kamzor hai to system **"insufficient context"
   flag** kare, blind reason na kare.
4. **Hard constraints kabhi na chhoote.** Locked decisions, active requirements, open conflicts — score kuch
   bhi ho, **hamesha context me**.

Ye 4 baatein har CP-11/12/13 ticket ke acceptance me baked hain (neeche **Strength Checklist** = rigor bar).

---

## 🗺️ MASTER CHECKPOINT SEQUENCE (Phase 2 — poora, reconciled)

*Stateful + full-platform + market-standard trust-hardening — sab ek ordered list me. Detailed tickets neeche.*

| CP | Naam | Kya | Gate |
|---|---|---|---|
| **CP-10** | **Project & Conversation** | project CRUD + conversation model (project-linked chat); har analyze = ek turn | self |
| **CP-11** | **Persistence & Versioning** | decision store, accept flow, immutable versions, history API | self |
| **CP-12** | **Ingestion + Embeddings + Graph** | item ingest, embeddings, auto edge-extraction, **no-orphan**, integrity, **+ temporal validity (P0)** | self |
| **CP-13** ⭐ | **Retriever** | anchor extract → hybrid (vector+sparse+graph+recency) → fuse → rerank → hard-constraint floor → missing-context guard → **recall@k eval gate** | 🔴 human |
| **CP-14** | **Faithfulness Gate + Conflict Detection** | **grounding gate (P0)** — claim retrieved-context me trace ho warna reject; conflict detect → `conflicts_with` edges + surface | 🔴 human |
| **CP-15** | **Interactive Resolution + Write-back** | assumption/conflict resolve, **clarification loop** (planner-gated), **knowledge/graph write-back on accept** (roadmap Ch6 §11) | 🔴 human |
| **CP-16** | **Verification Hardening + Freeze** | Self-RAG **faithfulness critic** (structural se upgrade), freeze threshold **T** benchmark se, freeze flow | 🔴 human |
| **CP-17** | **Feedback / Learning loop** | accept/challenge/reverse outcomes → confidence calibration + ranking tuning (Trace→Reason→Learn→Replay) | self |
| **CP-18** | **Frontend / UX** | chat UI, decision cards (accept/challenge/recommend), project dashboard, conflict/alert feed, provenance view, WS streaming | 🔴 human |
| **CP-19** | **Auth & Multi-tenancy** | users, project ownership, access control, role-based memory | self |
| **CP-20** | **Domain Grounding + Proactive Watchdog** | standards/datasheets/part-DB ingest; naya knowledge → purani decisions re-check → **alerts** | 🔴 human |

**Sequence logic:** project+conversation (foundation) → persist → data+graph → retrieve → trust gates
(faithfulness+conflict) → interactive+write-back → verify+freeze → learn → UI → auth → domain-grounding+watchdog.
Har step pichle par depend karta hai. P0 trust items (temporal validity, faithfulness) CP-12/14 me baked.

> Neeche ke detailed ticket-sections (CP-10..15) purane numbering me hain; ye master table unhe reconcile +
> extend karti hai (CP-16..20 naye). Build karte waqt is master sequence ko follow karo.

---

## CP-10 — Persistence & Versioning (decision store)
*Accepted decisions ko immutable + versioned save karo. Foundation — pehle ye.*

- [ ] **10.1 DecisionStore engine** — `DecisionRecord` (already in db/models.py) ke upar save/get/list.
  `new_decision_version()` use karke naya version banana. AC: save → row; get by id → latest; list by project.
- [ ] **10.2 Accept flow + versioning** — decision accept → `status=accepted`, immutable. Re-accept (edited)
  → `version=n+1`, `supersedes=<prev>`, prev untouched. AC: v1 accept → v1 immutable; edit+accept → v2 linked;
  history chain retrievable.
- [ ] **10.3 Decision API** — `POST /v1/decisions` (persist proposed/accepted), `GET /v1/decisions/{id}`,
  `GET /v1/decisions/{id}/history`, `GET /v1/projects/{pid}/decisions`. AC: endpoints round-trip; history returns chain.
- [ ] **10.4 Contract** — agar `decision.schema.v1` me `version`/`supersedes`/`project_id` missing hain to
  contract-change ticket (bump `$id` if breaking, update all consumers + tests same commit).

**Gate:** self-merge (low risk). Report + notify.

---

## CP-11 — Project State Ingestion + Embeddings
*Retriever ko fetch karne ke liye pehle DB me data bharna hai.*

- [ ] **11.1 Project item ingestion** — `POST /v1/projects/{pid}/items` requirements/decisions/docs store kare
  (typed: requirement/decision/assumption/constraint→requirement/document). AC: post → stored + queryable.
- [ ] **11.2 Embedding provider** — `embed(text)->vector`. Stub = deterministic (EMBED_DIM current), real =
  go-live pe pluggable (behind interface, jaise model_router). AC: stub deterministic + dimension match.
- [ ] **11.3 Chunk + embed pipeline** — ingested docs → `DocumentChunk` rows with embeddings. AC: N docs →
  chunks + vectors stored; count correct.
- [ ] **11.4 Edge extraction (graph connectivity)** — har naya decision/requirement ingest hone pe uske
  relations (depends_on/affects/constrains/supersedes/references) detect karo (heuristic + LLM-assisted) aur
  `graph_edges` me banao. AC: naya item ≥1 edge ke saath link ho; extracted edges validated (11 RelationType).
- [ ] **11.5 No-orphan guarantee** — koi decision bina kisi edge ke store na ho; agar koi relation na mile to
  item `needs_linking` flag ho (silently orphan nahi). AC: orphan insert → reject/flag, accept nahi.
- [ ] **11.6 Graph integrity checks** — `supersedes` acyclic (DAG), dangling-edge nahi, symmetric edges
  (`conflicts_with`) dono taraf. AC: cycle/dangling insert → detected + blocked.

**Gate:** self-merge. Report + notify. **(Graph = core → connectivity yahin se enforce hoti hai.)**

---

## CP-12 — Retriever (graph + vector + recency)  ⭐ core, accuracy-critical
*project_id + question → poore project ka relevant context KHUD assemble. `retrieval.py` stub implement.*
*Ye phase ka sabse critical CP hai — retrieval galti = reasoning fail. Har ticket measurable.*

**Query understanding**
- [ ] **12.1 Anchor extraction** — question se entities/refs nikaalo (kaunsa decision/requirement/component
  baat ho rahi) → graph traversal ke seed nodes. AC: known entity question → sahi anchors.

**3 signals**
- [ ] **12.2 Semantic signal (dense)** — question embed → `document_chunks` pgvector **cosine kNN** (HNSW/IVFFlat
  ANN index). AC: known-similar item top-k me.
- [ ] **12.3 Lexical signal (sparse)** — keyword/BM25-style match (exact terms, part numbers, spec values jo
  embeddings miss karte hain, e.g. "REQ-4", "±0.1 pH"). AC: exact-term item retrieve ho jab vector miss kare.
- [ ] **12.4 Graph signal — weighted seeded traversal + expansion** — anchors se edges pe traverse; score =
  edge-type-weight × hop-decay (exponential `λ^hop`). Retrieved seeds ko **N-hop expand** karke connected
  decisions/conflicts pull karo — **yahi hidden-dependency + conflict surface karta hai (core purpose)**.
  Explainable path per candidate. AC: linked item high score + path; conflict edge pe conflict aaye; unlinked ~0.
- [ ] **12.5 Recency signal** — exponential time decay → 0..1. AC: naya > purana.

**Fusion + precision**
- [ ] **12.6 Fusion** — dense+sparse+graph+recency ko **Reciprocal-Rank-Fusion (ya calibrated weighted
  `rank_score`)** se combine → over-fetch wide (miss risk kam). AC: fused top-k ⊇ har signal ke strong hits.
- [ ] **12.7 Rerank** — over-fetched set ko cross-encoder/LLM relevance-rerank karke precision badhao, phir
  `ContextEngine.build()` compress. AC: rerank ke baad precision@k improve (eval se).
- [ ] **12.8 Hard-constraint floor** — locked decisions, active requirements, **open `conflicts_with`** —
  score kuch bhi ho, **hamesha include**. AC: relevant hard-constraint kabhi drop na ho.
- [ ] **12.9 Coverage / missing-context guard** — retrieved set ke entities ke saath koi zaroori linked item
  chhoot to nahi gaya (graph coverage check); agar coverage/confidence low → **"insufficient context" flag**
  (blind reason nahi). AC: critical item hata do → system flag kare, confident-galat na de.

**Wire + measure**
- [ ] **12.10 Assemble + wire** — candidates(+signals) → `ContextEngine.build()` → DecisionEngine.
  `/v1/analyze` ab `{project_id, question}` le (context_items optional override). Response me **provenance**
  (kaunse items, kis path/signal se). AC: bina manual context ke decision + provenance aaye.
- [ ] **12.11 Retrieval eval harness (recall@k, precision@k, nDCG, MRR)** — labeled gold set ("is question ke
  liye ye items zaroor chahiye") + metrics. **Merge-gate:** recall@k threshold se neeche → merge nahi;
  regression (recall gira) → block. AC: eval runs in CI-style; numbers reported, gate enforced.

**Gate:** 🔴 **HUMAN** — retrieval quality sab par asar daalti hai; recall@k numbers ke saath review.
Report with retrieval examples + eval scores + notify.

---

## CP-13 — Conflict Detection
*Naya decision/requirement purane se takraye to pakdo aur surface karo.*

- [ ] **13.1 Conflict detector** — naya item store hone pe existing state se contradiction check → `conflicts_with`
  edge (graph). Heuristic + (go-live) LLM-assisted. AC: contradictory pair → edge banta; unrelated → nahi.
- [ ] **13.2 Surface conflicts** — decision output me active conflicts flag; `GET /v1/projects/{pid}/conflicts`.
  AC: endpoint lists open conflicts with the two sides.

**Gate:** self-merge. Report + notify.

---

## CP-14 — Interactive Resolution (assumption / conflict / clarification)
*Engineer resolve kare → system re-reason kare → naya version. THE interactive loop.*

- [ ] **14.1 Assumption state** — `Assumption` model me `status` (open/resolved), `resolution`, `resolved_by`.
  **Contract-change** (bump if breaking, all consumers + tests same commit). AC: assumption resolve state carry.
- [ ] **14.2 Resolve assumption** — `POST /v1/decisions/{id}/assumptions/{aid}/resolve {resolution}` → record →
  **re-reason** with resolved info → new decision version (CP-10 flow). AC: resolve → v+1, confidence update,
  v-prev immutable.
- [ ] **14.3 Resolve conflict** — `POST /v1/conflicts/{cid}/resolve {decision}` → edge closed + affected
  decisions re-evaluated. AC: resolve → conflict closed, history kept.
- [ ] **14.4 Clarification loop** — jab `needs_clarification`, `POST /v1/analyze/{session}/answer {answers}` →
  answers context me add → continue reason. AC: answer → decision aaye (no manual re-send).

**Gate:** 🔴 **HUMAN** — state mutation + re-reason semantics. Report + notify.

---

## CP-15 — Verification Hardening + Freeze Threshold
*Phase-1 ke deferred smalls. Freeze = consequential → human.*

- [ ] **15.1 Real critic LLM** — verify `_find_issues` ko structural-only se upgrade: independent critic model
  jo assumptions/claims challenge kare (still lower-only confidence, freeze_blockers preserve). AC: weak
  assumption pe issue raise + confidence drop.
- [ ] **15.2 Freeze threshold T** — scored benchmark runs se `T` derive (STOP condition: fabricate mat karna —
  data se aaye). Freeze gate `T` ke peeche enable. AC: below-T → freeze blocked; at/above + no freeze_blockers → eligible.
- [ ] **15.3 Freeze flow** — `verified` + eligible → human-approved freeze → `status=frozen` (immutable final).
  AC: freeze sirf gate+human ke through; autonomous nahi.

**Gate:** 🔴 **HUMAN** (freeze). Report + notify.

---

## 🎯 Graph & Retrieval Strength Checklist (the rigor bar — "ganit")

*Ye wo bar hai jise Phase 2 clear kare. Graph core hai + retrieval accurate na ho to reasoning fail. Har item
measurable / enforceable hai.*

**Graph strength (decisions interconnected, core engine)**
- [ ] **No orphans** — har decision ≥1 typed edge se connected (CP-11.5). Orphan-rate metric = 0.
- [ ] **Auto edge extraction** — ingest pe relations detect + validate (CP-11.4); avg node degree track.
- [ ] **Integrity** — `supersedes` DAG (no cycles), no dangling edges, `conflicts_with` symmetric (CP-11.6).
- [ ] **Explainable paths** — har graph-retrieved item ka "kis path se aaya" returnable (audit).
- [ ] **Health metrics** — orphan-rate, avg-degree, connected-components, cycle-count reported per project.

**Retrieval strength (accurate ya fail)**
- [ ] **Hybrid** — dense (vector) + sparse (lexical/BM25) + graph expansion + recency, fused (RRF/weighted).
- [ ] **Graph expansion** — seed retrieval ke baad N-hop expand → hidden dependencies + conflicts surface.
- [ ] **Over-fetch → rerank → compress** — recall wide, phir precision (cross-encoder/LLM rerank).
- [ ] **Hard-constraint floor** — locked decisions/requirements/open-conflicts hamesha in-context.
- [ ] **Missing-context guard** — coverage low → "insufficient context" flag, blind reason nahi.
- [ ] **Measured, not guessed** — recall@k / precision@k / nDCG / MRR on a gold set; **recall gate blocks merge**.
- [ ] **Regression-proof** — recall gira to CI-style gate fail (accuracy kabhi peeche na jaye).
- [ ] **Tunable + calibrated** — k, hop-limit, edge-weights, decay-λ, floor-set eval set pe calibrate.

**The math being used (ganit, reference)**
- Vector: cosine similarity + ANN (HNSW/IVFFlat). Sparse: BM25/term-match. Recency: exponential decay.
- Graph: edge-weight × hop-decay traversal; (optional stronger) Personalized PageRank; shortest-path for conflict chains.
- Fusion: Reciprocal Rank Fusion (or calibrated linear `rank_score`). Rerank: cross-encoder relevance.
- Metrics: recall@k, precision@k, nDCG, MRR (retrieval); orphan-rate, degree, components (graph).

**Definition of "strong enough" (Phase-2 exit bar):** orphan-rate 0 · graph integrity checks green ·
retrieval recall@k ≥ target on gold set · missing-context guard demonstrably fires when a critical item is
removed · every retrieved item explainable.

---

## 🧭 Market-Standard Hardening (2026) — critical additions

*End-to-end workflow ko market best-practice (agentic RAG, Self-RAG faithfulness, context-graph temporal
validity, feedback loops) se compare karke nikale gaps. Do P0 trust-critical hain. (Detail:
`EDOS-Critical-Review-vs-Market.md`.)*

- [ ] **P0 — Faithfulness / grounding gate** *(CP-12/CP-15 ke saath)* — decision return karne se pehle har
  material claim retrieved-context me trace ho (LLM-judge/NLI); ungrounded → **reject/downgrade, silently
  return nahi**. `evidence[]` already hai — enforce karo. Metric: faithfulness ≥ target, citation-precision ≥ target.
  AC: hallucinated claim (context me nahi) → blocked; grounded → pass.
- [ ] **P0 — Temporal validity ("trust now") in graph** *(CP-11/CP-13 upgrade)* — har node/edge pe validity
  state (active/superseded/stale/conflicted) + timestamp. Retrieval **currently-valid prefer** kare; stale
  explicitly flag. Unlocks proactive watchdog. AC: superseded decision retrieval me demote/flag ho.
- [ ] **P1 — Self-RAG verify** *(CP-15.1 expand)* — structural-only se upgrade: real critic + **faithfulness
  scoring**. AC: unsupported claim → issue + confidence drop.
- [ ] **P1 — Agentic / ReAct multi-hop** *(CP-12 upgrade)* — complex decision pe reason→"X missing"→retrieve
  more→reason again. Simple pe single-pass (cost). AC: multi-hop question pe 2nd retrieval trigger ho.
- [ ] **P1 — Feedback / learning loop (CP-18, naya)** — accept/challenge/reverse outcomes → confidence
  calibration + ranking-weight tuning. Loop: Trace→Reason→Learn→Replay. AC: outcome signal calibration ko move kare.
- [ ] **P2 — Memory tiers** — hot (conversation) / semantic (project) / procedural (domain rules+patterns) formalize.
- [ ] **P2 — Provenance-chain enforcement** — full decision trace (retrieved set, scores, prompt, faithfulness) stored + surfaced (audit).
- [ ] **P2 — Dynamic compression via summarize** *(CP-12.7 upgrade)* — low-ranked drop nahi, summarize.

**Trust bar (exit):** faithfulness gate green · temporal validity enforced · verify does faithfulness scoring ·
every decision fully traceable.

---

## Cross-cutting (har CP me dhyan)
- Har naya engine `src/edos/engines/` me single-responsibility. Retriever ≠ Context Engine (retriever fetch+signals; context rank+compress).
- Sab LLM output schema-validated (repair/reject, never persist malformed).
- Har ticket: test added + full suite green + `PROGRESS.md` update + backlog box check + commit.
- Contract change = same-commit consumers + tests + `$id` bump if breaking.

## Sequence (why this order)
```
CP-10 persist ──► CP-11 ingest+embed ──► CP-12 retriever ──► CP-13 conflict ──► CP-14 resolve ──► CP-15 verify+freeze
   (foundation)      (data to fetch)       (auto context)     (detect)          (close loop)       (harden+lock)
```
Har step pichle par depend karta hai — persist bina versioning nahi, retriever bina data nahi, resolve bina persist+conflict nahi.

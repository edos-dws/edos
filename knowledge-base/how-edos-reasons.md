# EDOS — How It Works

**A complete, detailed walkthrough of the reasoning workflow: every component and every step, explained to
answer one question — "How does it actually work?"**

> EDOS (Engineering Decision Operating System) is a decision-intelligence tool for embedded-systems
> engineering. It is **not a chatbot**. It reasons *with* an engineer like a senior team would: it reflects
> its understanding first, reasons through project-specific frameworks, proposes an argued decision, lets the
> engineer keep re-reasoning, and only finalizes the decision when the engineer **accepts** it.
>
> Core principle: **"AI reasons. Software orchestrates."** The intelligence is in how the software organizes,
> weights, and validates knowledge before and after the LLM — not in the LLM alone.

---

## Table of contents
1. [The mental model in one picture](#1-the-mental-model-in-one-picture)
2. [The reasoning brain (ERC core)](#2-the-reasoning-brain-erc-core)
3. [The four building blocks](#3-the-four-building-blocks-spine--lenses--weighting--scaffold)
4. [The workflow, step by step](#4-the-workflow-step-by-step)
5. [Anatomy of the decision card](#5-anatomy-of-the-decision-card)
6. [Continuous reasoning, revision & accept](#6-continuous-reasoning-revision--accept)
7. [Consistency: GraphRAG & contradiction detection](#7-consistency-graphrag--contradiction-detection)
8. [Robustness & graceful degradation](#8-robustness--graceful-degradation)
9. [Two worked examples](#9-two-worked-examples)
10. [Code & file reference map](#10-code--file-reference-map)
11. [Design invariants](#11-design-invariants)

---

## 1. The mental model in one picture

The single most important idea: **cheap deterministic software decides *what to reason about and what to
ask*; an expensive frontier LLM does the *actual reasoning*.** A few keywords never produce shallow reasoning
— when project signal is thin, EDOS asks more questions instead of guessing.

```
                    CHEAP · DETERMINISTIC (software orchestrates)                 EXPENSIVE · DEEP (AI reasons)
       ┌──────────────────────────────────────────────────────────┐   ┌──────────────────────────────────────┐
QUERY→ │ 1. SPINE      classify the project's direction (10 axes)  │   │ FRONTIER LLM reasons over:             │
       │ 2. WEIGHTING  score all 18 lenses for THIS project+topic  │ → │  • the DEEP lens frames (full text)    │ → CARD
       │ 3. SCAFFOLD   assemble spine + weighted lens frames        │   │  • full retrieved project context      │  (a
       │ 4. FRAME      show understanding + lenses + ask unknowns   │   │  • the engineer's answers              │  proposal)
       └──────────────────────────────────────────────────────────┘   │  • prior related decisions (GraphRAG)  │
                                                                       └──────────────────────────────────────┘
                                                                                         │
                             REVISE ⟲  (re-reason → new immutable version, still a proposal) ─────────────────────┤
                                                                                                                  ▼
                                                                                                     ACCEPT → crystallize
                                                                                              (write-back to graph + learning)
```

---

## 2. The reasoning brain (ERC core)

**File:** `src/edos/prompts/templates/erc_core.md` — injected into every reasoning prompt via the `{{ERC_CORE}}`
marker (substituted by `registry.load_template()`).

This is the persona and discipline that governs *every* LLM call, before any project-specific tuning. It has
four parts:

### 2a. Four senior archetypes
The LLM reasons as a composite, applying whichever the decision needs:
- **Senior embedded engineer** — derives budgets from first principles before naming a part; reads datasheets
  skeptically (typical vs max, "guaranteed by design" vs tested); thinks in worst-case corners & derating.
- **Embedded-Linux / systems engineer** — boot chain (ROM→SPL→bootloader→kernel→userspace), mainline-vs-vendor-BSP
  fork, real-time determinism, A/B OTA, flash endurance, CVE surface — and *whether Linux is the right tier at all*.
- **Principal engineer** — lifecycle & production: second-source, EOL/allocation, whole-BOM cost at volume,
  which decisions are one-way doors.
- **Solution architect** — decomposes the system, defines interface contracts, separates the load-bearing
  decision from the detail.

### 2b. The reasoning method
- **Constraints before options** — derive the governing budgets first (current, energy, timing, memory,
  thermal, cost); a recommendation with no derived budget is a guess.
- **Show the line, and the runner-up** — state the chosen option as the end of a visible chain, and name the
  #2 option, how narrow the gap is, and what tipped it.
- **Second-order ripple is mandatory** — every choice forces things elsewhere (power→thermal→EMC→BOM→cert);
  flag whether it invalidates an earlier decision.
- **Diagnosticity** — weigh only factors that actually separate the options.
- **Separate "likely" from "confident"** — probability of the outcome ≠ confidence in the reasoning.

### 2c. Break-the-loop mandate
Actively catch the framing failures that cost teams weeks: *wrong problem*, *premature part-lock*,
*local-optimum-global-blowout*, *software-as-an-afterthought*, *reference-design cargo-culting*,
*availability-blindness*, and the *silent contradiction* with a prior decision.

### 2d. Truth & safety discipline (pre-existing, preserved)
Never invent datasheet values; separate FACTS / ASSUMPTIONS / INFERENCE / RECOMMENDATION; calibrate severity
to real consequence; never declare a design "verified/frozen" (that is a separate human gate).

---

## 3. The four building blocks (spine → lenses → weighting → scaffold)

These are what make EDOS **project-conditioned**: the same question on two different projects produces
different reasoning emphasis. Importance is **never baked platform-wide** — it is derived per project + per
decision.

### 3a. SPINE — the project's "direction fingerprint"
**File:** `src/edos/engines/spine.py`

The spine classifies a project along **10 architecture-defining axes**. Fix these and most downstream lens
weights follow causally. It is a **pure, deterministic function of the project's text** — no LLM, no
fabrication.

| # | Axis (`key`) | Example values | Importance |
|---|---|---|---|
| 1 | `compute_tier` | mcu · rtos · linux · hybrid · fpga · dsp | 1.0 |
| 2 | `realtime` | hard · soft · firm · none | 0.9 |
| 3 | `power_source` | mains · battery · harvesting | 0.9 |
| 4 | `connectivity` | none · wired · wireless | 0.9 |
| 5 | `criticality` | consumer · industrial · medical · automotive · avionics | 0.9 |
| 6 | `volume` | one_off · low · mass | 0.7 |
| 7 | `data_char` | control · streaming · sensor_fusion · edge_ai | 0.7 |
| 8 | `environment` | benign · harsh | 0.6 |
| 9 | `markets` | us · eu · global | 0.6 |
| 10 | `form_factor` | unconstrained · size_bound · wearable · sealed | 0.6 |

**How classification works (`classify(corpus)`):**
1. Lowercase the whole project corpus (all items, not just the query).
2. For each `"axis:value"`, count trigger occurrences using **whole-term matching** — `count_term()` uses the
   regex `(?<![a-z0-9])term(?![a-z0-9])`. This is critical: a naive substring `in` test wrongly matched
   `rf` inside "su**rf**ace", `ecu` inside "s**ecu**re", `npu` inside "i**npu**t", `pid` inside "ra**pid**" —
   silently corrupting the classification. The boundary matcher blocks letter/digit-embedded false hits while
   still allowing `wi-fi`, `-40`, `iso 26262`, etc.
3. For each axis, the value with the most hits wins. **An axis with zero hits stays `unknown`** — it is
   returned in `SpineResult.unknown` to be **asked**, never guessed.

**Output — `SpineResult`:** `{values: {axis→value}, unknown: [axis,…], signals: {"axis:value"→hitcount}}`.
The `signals` are an audit trail (the non-fabricated basis for each derived value).

`framing_questions(result, max_q=3)` returns questions for the highest-importance UNKNOWN axes — this is the
"ask, don't guess" mechanism.

### 3b. LENS LIBRARY — 18 domain reasoning frameworks
**File:** `src/edos/engines/lenses.py`

A *lens* is the set of principal-level checks EDOS applies when a domain concern is load-bearing. Each is a
`Lens` dataclass:

```python
Lens(
  id,                  # e.g. "power"
  title,               # "Power (source, rails, regulation, low-power)"
  affinities,          # {"spine_axis:value" -> float}  how a spine position raises this lens
  structural_triggers, # ("battery","ldo","buck",...)   substrings that raise it if present
  scan_line,           # one-line blind-spot floor — ALWAYS present, never dropped
  base = 0.15,         # baseline salience before any signal
  frame_file = None,   # "power.md" -> the full reasoning frame (deep text), loaded on demand
)
```

The 18 lenses span: **compute · realtime · memory · firmware_arch · debug_bringup · peripherals_io ·
clocking_analog · power · connectivity_rf · pcb · mechanical_enclosure · thermal · reliability_safety ·
security · certification · manufacturing**, plus two **cross-cutting constraints** — **bom_supply** and
**cost** (these can *veto* the technically-best part; the weighting engine floors them).

**All 18 lenses carry a full reasoning frame** (`src/edos/prompts/lenses/*.md`) and a one-line `scan_line`.
Scan-vs-deep is decided by **weight**, not by whether a frame exists: the top-weighted lenses (capped at 5)
inject their full frame; the rest inject their scan_line (the blind-spot floor). A lens is **never dropped** —
weighting sets *depth*, not presence.

### 3c. WEIGHTING — importance derived per project + decision
**File:** `src/edos/engines/lens_weighting.py`; entry point `weigh(spine, topic, project_corpus, coverage, overrides)`.

For every lens, the raw score is:

```
score = base
      + Σ spine-affinity contributions          # Layer 1: causal, from the direction fingerprint
      + BETA_TOPIC(0.5) · topic_relevance         # Layer 2: this specific decision's topic
      + GAMMA_STRUCTURAL(0.3) · structural_presence  # actual components/facts present in the project
      + learned term (±DELTA_LEARNED = ±0.10)     # self-tuning: outcomes on similar-direction projects
```

The **learned term** is the self-tuning loop: when a decision is accepted, the lenses that were load-bearing
(deep) for it get a small boost *for that project's direction* (keyed by each spine `axis:value`); reversed
penalises them. Stored in the `lens_feedback` table, read back via `feedback.lens_learned_weights`, and bounded
to ±0.10 so it nudges the principled signal, never overrides it.

Then, applied over the raw scores:

1. **Confidence flattening** — pull weights toward the mean by a *confidence* factor, so a vague project
   doesn't over-commit (and the framing intake asks instead):
   `confidence = max(coverage, spine_confidence)` where `spine_confidence = known_axes / total_axes`.
   *This was a fixed bug:* keying flattening on `coverage%` alone washed out a **confident** spine at low
   coverage. A crystal-clear direction (many axes known) is reliable even when coverage% is low, so we take
   the stronger of the two signals.
2. **Engineer overrides win** — a pinned weight replaces the computed one.
3. **Constraint floor** — `bom_supply` and `cost` are always ≥ `CONSTRAINT_MIN(0.5)` (they must always surface).
4. **Blind-spot floor** — every lens is ≥ `BLIND_SPOT_FLOOR(0.08)`.

**Depth selection:** lenses are ranked by weight; the top **`DEEP_TOP_N(5)`** that also clear
**`DEEP_THRESHOLD(0.55)`** *and* have a `frame_file` become **DEEP** (their full frame is loaded). Everyone
else is **SCAN** (scan_line only). Output is a list of `LensWeight(lens_id, title, weight, deep, reason)` —
the `reason` is an audit string ("spine: power_source:battery; topic match (1); present in project").

### 3d. SCAFFOLD — the injected reasoning block
**File:** `src/edos/engines/reasoning_scaffold.py`; entry `build_scaffold(session, project_id, topic)`.

It ties everything together for one decision:
1. Gather the project corpus (all item content).
2. `spine.classify(corpus)` → the fingerprint.
3. `coverage_report(...)` → coverage fraction (0–1) for the flattening.
4. `lens_weighting.weigh(...)` → the ranked weights.
5. Split into **DEEP** (load full frame) and **SCAN** (scan_line).
6. Render one text block:

```
## PROJECT DIRECTION (spine — derived from this project's context)
- power_source: battery
- connectivity: wireless
- unknown (not yet established): realtime, data_char, markets

## REASON WITH THESE LENSES (weighted for THIS project and THIS decision)
### Reason through these thoroughly (load-bearing for this decision):
<full Power frame> … <full RF frame> …
### Also scan these for blind spots — stay brief, but do not skip:
- **Memory** — Does the footprint fit with margin…
- **Security** — Is there a root-of-trust…
```

This block (~2,000 tokens at 5 deep frames; the deep-dive prompt budget is larger) is prepended to the
deep-dive `decide` prompt. The `deepdive_prompt.v1.md` explicitly instructs the LLM to reason through the
DEEP frames, honour the SCAN lenses as a blind-spot checklist, and respect the spine ("a battery project and
a mains project must not get the same answer") — while never fabricating a value to satisfy a lens.

---

## 4. The workflow, step by step

**Engine:** `src/edos/engines/deepdive.py` · **API:** `src/edos/api/app.py` · **UI:** `frontend/index.html`.

### Step 0 · Project knowledge (before the query)
The engineer adds requirements / datasheets / constraints / prior decisions (`POST /v1/projects/{id}/items`).
Each is persisted and **embedded** for semantic retrieval; rich items are also run through **fact extraction**
(atomic parameters become their own retrievable items). Both embedding and extraction are **best-effort** — a
provider/quota outage never fails the ingest (the item persists without its semantic chunk).

### Step 1 · The query
The engineer states a decision topic, e.g. *"Select the power regulation approach for the coin-cell rail."*

### Step 2 · Spine classification (deterministic router)
`spine.classify_project(session, project_id)` reads the project corpus and produces the fingerprint + unknown
axes. **No reasoning happens here** — it only routes.

### Step 3 · Reasoning-first FRAME
`deepdive.plan_frame()` → `POST /v1/projects/{id}/deepdive/frame` returns:
```
{ topic, understanding, spine: [lines], framing_questions: [{axis, q}], lenses: [{id,title,weight,deep,reason}] }
```
The UI shows: **"I understand you're deciding X"**, the **project direction** chips, **"I'll reason hardest
about"** (the weighted deep lenses), and **framing questions** for the unknown axes. The engineer can correct
the framing and (by design) override lens weights *before* EDOS commits to reasoning. This runs **without any
embedding call** — it is fully available even during an embedding-provider outage.

### Step 4 · Targeted questions (need-driven, 0–5)
`plan_questions()` → `POST /v1/projects/{id}/deepdive`. The lite LLM proposes questions, each with a
"WHY AM I ASKING?" rationale. Then **skip-known** drops any question already answered by the retrieved project
context (a 0.7·lexical + 0.3·embedder blend, so the offline stub can't fabricate a skip). Fewer is better;
five is a ceiling, not a target. **Answers become facts/context — never assumptions.**

### Step 5 · Adaptive follow-up (0–2)
`follow_up()` → `POST /v1/projects/{id}/deepdive/followup`. It **always** runs a deterministic
contradiction check (does an answer conflict with a stored decision?) plus optional LLM judgment, capped at 2.
Empty ⇒ ready to decide.

### Step 6 · Decide (the real reasoning)
`decide(session, project_id, topic, answers)`:
1. Persist the answers as context.
2. `_gather_context()` — retrieve + rank + rerank + label the relevant project knowledge, **plus prior
   related decisions via GraphRAG** (`_related_decisions_context`).
3. `_reasoning_scaffold()` — build the spine + weighted-lens scaffold text.
4. Call the frontier LLM: `router.execute(Capability.deepdive, {mode:"decide", topic, answers, context,
   reasoning_scaffold}, schema=DECISION_CARD_SCHEMA, tier=Tier.frontier)`.
5. `_card_from_llm(out)` — **coercion**: the LLM's payload (which may label fields its own way) is mapped onto
   the strict contract; the whole `detail` object (runner_up, blind_spots, tripwires, provenance) is carried
   through. If the LLM is unavailable/malformed, a **deterministic heuristic** builds an honest card instead
   (options/criteria derived from topic + answers + context — never fabricated datasheet values).
6. Persist as a new decision with `status="recommended"` (a **proposal**).

### Step 7 · The card (a proposal) — see §5.

### Step 8 · Revise — see §6.

### Step 9 · Accept — see §6.

---

## 5. Anatomy of the decision card

The decision splits into a **contract-valid `Decision`** (summary, recommendation, confidence, status,
assumptions, risks, evidence — the locked `edos.decision.v1` schema) and a rich **`decision_detail`** envelope
(NOT the locked contract) carrying the card blocks:

| Block | What it is |
|---|---|
| **Recommendation** | The chosen option + prose reason. Verb-graded ("we recommend" vs "we suggest"). |
| **Runner-up** | `{option, gap: narrow/moderate/wide, tipped_by: […]}` — the #2 option, how close, and the 1–2 factors that tipped it. A recommendation with no named runner-up is a red flag. |
| **Blind spots** | Distinct from risks — the non-obvious things *outside the question's frame* (e.g. MLCC DC-bias derating, a sealed enclosure making a brownout unrecoverable). |
| **Risks** | Ways the chosen path can fail (severity · likelihood · mitigation). |
| **Assumptions** | The premises the recommendation *rests on* that the answers did NOT establish — each testable, each with `risk_if_wrong`. (The engineer's answers are facts, never assumptions.) |
| **Comparison matrix** | criteria × options, decision-specific (never a fixed template), exactly one `recommended`. |
| **Tripwires** (`review_conditions`) | Pre-committed conditions that would flip the decision ("if standby > 5 µA, re-model battery life"). |
| **Provenance** | Every number is tagged `(computed: <arithmetic>)`, `(datasheet)`, or `(inferred)` — so an untagged number is never mistaken for fact. |
| **Computed checks** (Step 8) | EDOS **re-verifies the model's own arithmetic** *and computes some budgets itself.* For every `(computed:)` figure the LLM emits a `{quantity, expression, result}`; `checks.verify_computations()` re-evaluates it with a safe AST evaluator (`safe_arith` — numbers and `+ − × ÷ ** ( )` only, **no code execution**) → ✓ verified / ✗ mismatch ("stated X, computes Y") / ○ unchecked. A wrong LLM sum is *caught, not shipped* (a claimed "30" for `12+8.4+21.2` is flagged as 41.6). In addition, `checks.auto_compute()` computes a few budgets **independently** from quantities stated in the project (thermal ΔT = P·Rθ; battery life = capacity ÷ labelled average current) — only when the inputs are unambiguous by unit — and folds them in as EDOS-computed ✓ facts. |
| **Decision impact** | If this changes, what else changes (impacted components/areas). |

The card is *argued, not asserted*: it shows what it beat, what it might be wrong about, what would change
it, and where each number came from. Even the degraded **heuristic** path now carries a runner-up (derived
from the #2 matrix option) so a degraded card is never structurally poorer than the contract.

---

## 6. Continuous reasoning, revision & accept

**The card is the closing move of a visible argument, not the opening one.** Reasoning stays continuous until
the engineer accepts.

- **Proposal state.** `decide` persists the decision as `status="recommended"` — a proposal, not final.
- **Revise (unlimited).** `revise(prior, instruction)` → `POST /v1/decisions/{id}/revise`. The engineer's
  instruction ("cost target moved to $1.50", "must also pass CISPR 25", "why not X?") is treated as
  authoritative new information; EDOS re-reasons with the prior card as the baseline and produces a **new
  immutable version** (v2, v3, …) — still `recommended`. Every prior version stays fetchable
  (`GET /v1/decisions/{id}/history`) — the full reasoning trail is kept.
- **Accept (crystallize).** `POST /v1/decisions/{id}/accept` sets `status="accepted"` and runs **write-back**
  (`writeback.process_accepted`) — folding the decision's knowledge into the project graph + embeddings.
  `POST /v1/decisions/{id}/outcome {accepted}` then drives the **feedback loop**: the context items that fed
  the decision get a `feedback_score` boost, so items that produce good decisions rank higher over time.

This whole flow is locked by an end-to-end test
(`tests/test_deepdive.py::test_continuous_reasoning_flow_until_accept`): frame → questions → proposal →
revise×2 (still recommended) → accept (accepted). No future change can silently make the card a one-shot
verdict again.

---

## 7. Consistency: GraphRAG & contradiction detection

EDOS's edge over vector-only RAG is that a new decision is reasoned **for consistency with the past**.

- **GraphRAG at decide-time** (`_related_decisions_context`): pulls the project's prior decisions (up to 10),
  ranks them by **full-body relevance** (cosine of topic-vector vs the decision's title **+ rationale**, not
  the title alone), keeps the top 3 with similarity ≥ 0.35, and feeds each — **with the premises it rests
  on** — INTO the reasoning context *before* the LLM reasons. So a contradiction surfaces instead of being
  made silently.
- **Contradiction check** (`findings._stance_contradictions`, run in the follow-up stage): for a set of
  curated opposed concepts — current sensing (shunt/hall), isolation, cooling, cell balancing, overcurrent
  protection, **compute tier (MCU/Linux), scheduling (RTOS/bare-metal), regulator (LDO/switcher), power
  source (battery/mains)** — it detects when the engineer's input takes a different stance than a stored
  decision and raises it to reconcile. This is the "it refused to accept a contradicting decision" behavior.
- Decisions are also **connected** in the project graph (`related_decisions` links + typed `conflicts_with`
  edges the watchdog reads).

*Current depth (honest):* decisions live in the decision store (not the item graph), so cross-decision
consistency is stance-based on curated concepts + full-body relevance ranking — multi-hop edge traversal
across the *item* graph is a designed future improvement. Full-body relevance quality depends on the live
embedder.

---

## 8. Robustness & graceful degradation

EDOS is built to degrade, never break:

- **Ingest survives provider outages.** Embedding and fact-extraction are best-effort; a `429`
  quota-exhaustion on the embedding API persists the item **without** its semantic chunk instead of 500-ing
  and losing the engineer's data.
- **The reasoning-first FRAME needs no embeddings.** Spine classification is pure text analysis, so the
  frame (understanding + direction + weighted lenses + framing questions) works fully even during an
  embedding outage. Only semantic retrieval degrades.
- **Decide falls back honestly.** If the frontier LLM is unavailable or returns malformed output, a
  deterministic heuristic builds a card from the topic + answers + context — and the UI marks it as degraded
  so a template is never mistaken for the model's reasoning.
- **Nothing is fabricated.** No invented datasheet values anywhere; missing inputs are named and asked.
- **Everything is immutable + auditable.** Every decision and revision is a versioned, fetchable record.

---

## 9. Two worked examples

### Example A — project-conditioned reasoning (MCU ≠ Linux)
Same topic — *"Choose the compute tier: bare-metal MCU vs an MPU running Linux"* — two water-quality devices:

| | **A · simple logger** (pH/TDS/temp, coin-cell, BLE, sealed) | **B · rich station** (camera turbidity + edge-ML + 4G + HMI, mains) |
|---|---|---|
| Spine | battery · wireless · consumer · sealed | mains · streaming · wireless · sealed |
| Reasons hardest about | **Power · Enclosure · RF · Cost** | **Thermal · Compute-tier · RF · PCB** |
| Compute-tier weight | 0.78 (deep, but power/BOM dominate) | **0.94** (streaming + ML = real compute demand) |

The *whole* decision context reweights — not a keyword flip. The principal rule EDOS applies (from the
compute-tier frame): **"Name the specific Linux feature that forces the MPU tier; if you can't, drop a tier."**

### Example B — the crystallized card (real live output)
Topic: *"Select the power regulation approach for the coin-cell rail"* (CR2032 / nRF52 / BLE / IP68):
- **Recommendation:** CR2032 direct to nRF52 internal DC-DC + 47 µF low-ESR cap; ~85 % efficiency
  `(datasheet)`, $0.00 incremental BOM.
- **Runner-up:** external buck-boost (TPS62840 class), gap *moderate* — tipped away by the sealed-IP68 PCB
  area constraint and the tight consumer BOM.
- **Blind spots:** MLCC DC-bias derating (22 µF → ~10 µF, TX-pulse brownout); sealed IP68 → no field rework;
  CR2032 IR spike near 0 °C (>500 Ω) → *"~4.0 V drop under 8 mA pulse `(computed)`"*.
- **Tripwires:** "standby > 5 µA → re-model life"; "internal DC-DC fails RF-spurious pre-compliance → switch
  to LDO"; "temp < −10 °C → re-size bulk cap".

---

## 10. Code & file reference map

| Concern | File(s) |
|---|---|
| Reasoning brain (persona/method) | `src/edos/prompts/templates/erc_core.md` |
| Spine classifier | `src/edos/engines/spine.py` |
| Lens library | `src/edos/engines/lenses.py` |
| Lens reasoning frames (deep text) | `src/edos/prompts/lenses/*.md` (9 files) |
| Weighting engine | `src/edos/engines/lens_weighting.py` |
| Scaffold assembly | `src/edos/engines/reasoning_scaffold.py` |
| Deep-dive flow (frame/questions/follow-up/decide/revise) | `src/edos/engines/deepdive.py` |
| Deep-dive prompt (modes: questions/followup/decide/revise) | `src/edos/prompts/templates/deepdive_prompt.v1.md` |
| Prompt registry & rendering | `src/edos/prompts/registry.py`, `render.py` |
| Model router (tiers, capabilities) | `src/edos/engines/model_router.py` |
| Retrieval / context engine | `src/edos/engines/retrieval.py`, `context.py` |
| Deterministic math verification (Step 8) | `src/edos/engines/checks.py` (`safe_arith`, `verify_computations`) |
| GraphRAG / contradictions | `deepdive._related_decisions_context`, `findings._stance_contradictions` |
| Ingestion (best-effort embed) | `src/edos/engines/ingestion.py` |
| Accept / write-back / feedback | `decision_store.py`, `writeback.py`, `feedback.py` |
| API endpoints | `src/edos/api/app.py` |
| Frontend (frame + card UI) | `frontend/index.html` |
| Companion knowledge-base docs | `./context-engine.md`, `./decision-flow.md`, `./embedded-reasoning-model.md` (this folder) |

---

## 11. Design invariants

- **AI reasons, software orchestrates** — the LLM never searches the project; the software assembles the
  context package and the LLM reasons only over it.
- **One responsibility per engine** — retrieval, spine, weighting, scaffold, decision each own one job.
- **Keywords route, the LLM reasons** — thin signal ⇒ more questions, never shallower reasoning.
- **Importance is derived per project, never baked** — the spine + weights are computed, shown, and
  overridable.
- **A lens is never dropped** — weighting sets depth; every concern keeps its blind-spot scan line.
- **Ask, don't guess** — an unknown spine axis is asked, not assumed.
- **Nothing is final until accept** — the card is a re-reasonable proposal that crystallizes only on accept.
- **Immutable + versioned** — every decision and revision is auditable; prior versions never mutate.

---

*This is the canonical "how it works" document for the EDOS reasoning workflow. Companion topic docs live in
this same `knowledge-base/` folder. Reflects the workflow as built and tested (358 passing tests at time of
writing). A copy for offline reading is kept at `mnt/EDOS-How-It-Works.md`.*

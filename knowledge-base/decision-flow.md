# EDOS Decision Flow — user ke prompt se decision tak

> Ye doc Deep Dive ka **current working flow** samjhata hai (Hindi-Roman). Poora detailed English walkthrough
> (spine · lenses · weighting · card anatomy · computed-checks) → dekho **[`how-edos-reasons.md`](./how-edos-reasons.md)**
> (canonical doc). Retrieval/context ka detail → [`context-engine.md`](./context-engine.md); spine + lens
> design → [`embedded-reasoning-model.md`](./embedded-reasoning-model.md).

---

## Poora flow (ek nazar me) — current version

```
USER ──"kaunsa decision le raha hu?"──► DEEP DIVE
  │
  ▼  STAGE 0 · SPINE  (deterministic router — reasoning nahi)
  │    Poore project-text se DIRECTION-FINGERPRINT (10 axes); jo pata nahi → UNKNOWN (ask, guess nahi)
  │
  ▼  STAGE 1 · REASONING-FIRST FRAME  (card se PEHLE, editable)
  │    • "Ye samajh raha hu…" (understanding)  • spine chips  • "in par sabse zyada sochunga"
  │      (project+decision ke liye WEIGHTED lenses)  • UNKNOWN axes ke framing questions
  │    → engineer framing/weights correct kar sakta
  │
  ▼  STAGE 2 · QUESTIONS  (need-driven 0–5, already-known SKIP)
  ▼  STAGE 2b · FOLLOW-UP  (0–2, sirf gap/contradiction pe)
  │
  ▼  STAGE 3 · DECIDE  (asli reasoning)
  │    SCAFFOLD assemble: spine + top-weighted lens FRAMES (deep) + baaki scan-lines (blind-spot floor)
  │      + retrieved context (rank→rerank→labeled) + GraphRAG (prior decisions) + user answers
  │    → FRONTIER LLM → Decision Card  → Coercion (rich card surface)
  │    → COMPUTED-CHECKS: LLM ka apna math AST se re-verify (✓/✗/○) [Step 8]
  │
  ▼  RESPONSE ── DECISION CARD = PROPOSAL (status "recommended", final NAHI)
  │    recommendation · runner-up · blind-spots · tripwires · provenance · computed-checks · matrix · assumptions
  │
  ▼  REVISE ⟲  (continuous re-reasoning — naya immutable version, ab bhi proposal) … jab tak
  │
  ▼  ACCEPT ── crystallize (writeback graph+embeddings) + feedback loop + assumptions tracked
```

> **Card decision ka closing move hai, opening nahi.** Reasoning **continuous** rehti hai jab tak user
> **accept** na kare; accept pe hi crystallize hota.

---

## Stage-by-stage — beech me actively kya hota hai

### Stage 1 — Questions (need-driven)
- Pehle **project ka apna knowledge** dhundhta hai (context engine se).
- LLM sirf **wahi sawaal** banata jo decision ko materially badle — **max 5, aur zaroori na ho to kam / zero.**
- Jo user pehle answer kar chuka / jo project me already hai → **skip** (dobara nahi poochta).
- **Zero-question path:** kuch poochna hi nahi to EDOS apni **understanding** dikhata hai — "ye samajh raha hu,
  agree?" → agree → seedha decide.

### Stage 1b — Follow-up (adaptive)
- User ke answers ke baad **0–2 follow-up**, sirf agar koi answer gap khole ya kisi stored decision se
  **contradict** kare. Warna kuch nahi.

### Stage 2 — Decide (grounded reasoning)
- **Context Engine** poora context assemble karta (labeled + capped): relevant items + **prior related
  decisions (GraphRAG)** + user ke answers. (Detail: `context-engine.md`.)
- Ye clean context + topic → **frontier LLM** → Decision Card banata.
- **Coercion:** LLM apne field-naam use karta (jaise `value`/`name`), par contract strict hai — coercion
  usko fit karta taaki **rich card surface ho, chup-chaap discard na ho** (pehle yahi bug tha).
- Model down/quota ho to **deterministic heuristic fallback** — kabhi tootता nahi (par tab "template"
  banner dikhta hai, taaki honesty rahe).

---

## Decision Card me kya hota hai
| Block | Kya |
|---|---|
| **Recommendation** | Chosen option + prose reason |
| **Comparison Matrix** | criteria × options (topic-derived, ek `recommended ★`) |
| **Assumptions** | jo EDOS ne **infer** kiya (user ke answers NAHI) — har ek me `risk_if_wrong` |
| **Risks & blind spots** | context-matched, **variable count** (fixed 3 nahi) |
| **Decision Impact** | agar ye badla to aur kya badlega (impacted components se derived) |
| **Coverage** | project-context kitna complete hai |

Sab **dynamic** — comparison matrix / baseline / risks static template nahi, decision ke hisab se.

---

## Response ke baad — system background me kya karti
1. **Persist + versioned** — decision immutable, har change naya version (audit trail).
2. **Answers → project knowledge** (embedded) → agli baar **re-ask nahi** (feedback: `context-engine.md` #1).
3. **Assumptions first-class** — A-id + lifecycle (`created → validated → challenged → invalidated`).
4. **Graph update** — related-decision edges, **cross-decision contradiction detect**.
5. **Coverage recompute** — 6 domains pe.
6. **Feedback loop (#7)** — jab decision **accept** hota (`/outcome`), jo items usne use kiye unhe **boost**
   (reversed pe penalise) → retrieval time ke saath **self-tune**.
7. **Watchdog** — baad me chup-chaap flag: **aged assumption** ya **cross-decision conflict**.

---

## Revise (Challenge ki jagah)
Decision card pe **"Revise Decision"** — user likhta hai kya update/clarify karna hai → EDOS us input ko
naya knowledge maan ke **dobara evaluate** karta hai → **naya version** banata (purana version history me
safe). Prior decision LLM ko baseline ki tarah milta hai.

---

## Naya vs purana
- **Pehle:** prompt → dhundhla retrieval → flat unlabeled context → LLM assume karta → generic card (aur wo
  bhi coercion-bug se discard hoke heuristic).
- **Ab:** prompt → **need-driven questions** → **semantic retrieve → rerank → labeled → GraphRAG** → LLM
  **grounded + consistent** reason karta → **rich card surface** → phir sab **persist + graph + coverage +
  feedback** update.

---

## Ek line summary
User topic deta hai → EDOS **sirf zaroori sawaal** poochta hai → project ki **apni knowledge + prior
decisions** pe grounded ek **defensible Decision Card** banata hai → aur phir sab kuch **yaad rakhta,
version karta, graph me jodta, aur outcomes se seekhta** hai.

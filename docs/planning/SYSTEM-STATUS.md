# EDOS — System Status: Kya Bana, Kya Baaki

**Date:** 2026-07-24
**Purpose:** Ek clear picture — abhi tak kya bana hai, kya baaki hai. Ye doc baad me **backlog** banane ka
base hai. (Abhi backlog nahi — sirf samajhne ke liye.)

---

## TL;DR (ek line me)

EDOS ka **"reasoning dimaag" ban chuka hai** — sawaal do + context do, wo structured engineering decision
deta hai (assumptions, risks, tradeoffs, verify, freeze-safety ke saath). **Jo baaki hai wo iske aas-paas
ka "memory + state" layer hai** — abhi system har request ke baad sab bhool jaata hai (stateless). Aage ise
**stateful** banana hai: context khud fetch ho, accepted decisions save hon, assumptions/conflicts resolve
ho sakein.

---

## Component-wise status

| Layer | Component | Status | Note |
|---|---|---|---|
| **Reasoning** | Decision Engine | ✅ Bana | context pe reason karke decision deta hai; context na ho to clarification maangta hai |
| | Context Engine (ranking/compress) | ✅ Bana | candidates ko rank + compress karta hai (par candidates tu deta hai, DB se nahi) |
| | Model Router | ✅ Bana | capability→tier routing; live LLM ya stub |
| | Prompts (versioned) | ✅ Bana | ERC-style decision/planner prompts |
| **Safety** | Verification Engine | ✅ Bana | decision critique; confidence sirf niche; freeze_blockers preserve (abhi structural-only critic) |
| | Freeze Gate | ✅ Bana par **DISABLED** | threshold set nahi (fail-safe); autonomous freeze band |
| **LLM** | Live provider (Gemini) | ✅ Connected | `gemini-3.6-flash` default; Anthropic + stub bhi supported |
| **Storage (DB)** | Tables: projects, decisions (versioned), graph_edges, document_chunks (pgvector) | ✅ Schema bana | **par API se wired NAHI** — analyze kuch save nahi karta |
| **API** | `/v1/ask`, `/v1/analyze`, `/v1/verify`, events + 2 websockets | ✅ Bana | sab **stateless** |
| **Memory/State** | **Retriever** (project se context khud fetch kare) | ❌ Stub only | `retrieval.py` = `NotImplementedError` |
| | **Persistence** (accepted decision save + version) | ❌ Nahi | analyze stateless hai |
| | **Assumption resolution** (resolve karke re-reason) | ❌ Nahi | `Assumption` me `status`/`resolved` field tak nahi |
| | **Conflict detection + resolution** | ❌ Nahi | graph me `conflicts_with` edge-type hai, par detect/resolve flow nahi |
| | **Clarification loop** (jawab do → aage badhe) | ⚠️ Aadha | questions pooch leta hai, par answer feed karke continue karne ka loop nahi |
| | Planner engine | ❌ Stub only | `planner.py` = `NotImplementedError` |

**Test health:** 29 test files, 121 tests green, CI deterministic (ruff pinned).

---

## Chhota example — abhi ka STATELESS flow

Water quality device. Tu abhi aise kaam karta hai:

```
1. TU khud likhta hai context_items (ref_id + content + signals) request me:
     REQ-1: "pH high-impedance, DO nA current..."  signals:{graph:0.9, semantic:0.95,...}
     REQ-4: "accuracy pH +/-0.1..."                 signals:{...}
2. POST /v1/analyze  { question, context_items }
3. Engine → context rank/compress → reason → decision return
4. Response me: recommendation "ESP32-C6", assumptions, risks, freeze_blockers
5. BAS. Kuch save nahi hua. Agli call ko ye decision yaad nahi.
   Agli baar phir se saara context tujhe manually bhejna padega.
```

**Do dikkat:**
- Context **tu** haath se banata hai (signals bhi manually).
- Decision accept kiya to bhi kahin **store nahi** hota — agli decision isse link nahi hoti.

---

## Aage ka STATEFUL flow (target) — same example

```
1. Ek baar project setup: requirements/decisions DB me daale jaate hain (project state).
2. POST /v1/analyze  { project_id, question }     ← ab sirf project_id + sawaal
3. RETRIEVER (naya): project_id se DB/graph/vectors se relevant items KHUD fetch kare,
   aur signals (graph-distance, embedding-similarity, recency) KHUD compute kare.
4. Context Engine (jo bana hai) → rank/compress
5. Decision Engine → reason → decision
6. Engineer decision dekhe → "Accept" kare
7. PERSISTENCE (naya): accepted decision ek IMMUTABLE VERSIONED RECORD ban ke save ho,
   uske assumptions/risks/conflicts bhi store hon, aur graph me link ho.
8. Baad me engineer assumption resolve kare → system us decision ko re-reason kare (naya version).
```

Farq: tu sirf **project_id + question** bhejega. Baaki system khud context laayega, decision save karega,
aur pichli decisions se link karega. **Yahi "persistent engineering brain" hai.**

---

## Accepted decisions kaise save honge (immutable + versioned)

Rule (CLAUDE.md): **decision kabhi jagah pe edit nahi hoti — naya version banta hai.**

Example — ESP32-C6 decision accept hui:

```
decisions table:
  id=DEC-3  version=1  status=accepted
  summary="Host MCU = ESP32-C6"
  confidence=0.85
  parent=DEC-2 (AFE architecture)      ← graph link
  assumptions=[{stmt:"ESP32 price $1.20-1.80", status:OPEN, risk_if_wrong:"..."}]
  created_at=...
```

Baad me engineer ne assumption resolve ki ("price confirmed $1.60 from distributor"):

```
  id=DEC-3  version=2  status=accepted
  supersedes=DEC-3 v1                   ← v1 immutable rehti hai, history bachi rehti hai
  assumptions=[{stmt:"ESP32 price $1.60", status:RESOLVED, resolved_by:"distributor quote"}]
  confidence=0.90                        ← assumption resolve hone se confidence badhi
```

- **v1 delete nahi hoti** — audit trail/history rehti hai.
- Har change = naya version, purane se linked (`supersedes`).
- Conflicts: agar naya decision kisi purane se takraye, `conflicts_with` edge banega aur engineer ko dikhega.

---

## Bade picture me — 3 theme baaki hain

Sab ek hi baat ke hisse: **"stateless reasoning function" → "stateful engineering brain".**

1. **Retriever** — project state se context khud fetch + signals compute (manual context_items khatam).
2. **Persistence + versioning** — accepted decisions/assumptions/conflicts DB me immutable+versioned save.
3. **Interactive resolution** — assumption resolve, conflict resolve, clarification-answer → re-reason loop.

(+ chhoti: verify ka real critic LLM go-live pe, freeze threshold benchmark se derive.)

---

## Retriever kaise context laayega (brief)

Hybrid — 3 signals nikaal ke maujuda `rank_score` (0.40·graph + 0.30·semantic + 0.15·recency + …) me daal do:

- **graph (0.40):** knowledge graph pe **weighted seeded traversal** — query ke anchor nodes se edges pe chalo,
  edge-type weight (`conflicts_with` high, `mentions` low) × hop-decay. Explainable + deterministic (PPR se
  behtar fit, kyunki "ye context kyu aaya" batana hai). Bonus: `conflicts_with` edge pe chalte hi conflict khud surface.
- **semantic (0.30):** question embed → `document_chunks` (pgvector) pe cosine kNN.
- **recency (0.15):** timestamp decay.

Naya fusion algorithm nahi chahiye — signals seedha existing weighted score me fuse. (RRF baad me optional.)

---

## Next step

Jab tu bole, is doc ke base pe **detailed backlog** banaunga — checkpoint-style tickets (jaise pehle CP-0..9
bana tha), har theme ke liye acceptance criteria + order ke saath. Abhi ke liye bas ye samajh:
**dimaag bana hai, memory baaki hai.**

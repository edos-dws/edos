# EDOS — Point 2: Full Platform Alignment & Planning (Implementation)

**Maqsad:** Platform ko sirf API nahi, **har user ke liye end-to-end accessible** banana. Tumne pura workflow
dobara explain kiya — main use canonical form me likh ke **roadmap + current code se cross-check** karta hu:
kitna aligned, kya bana, kya baaki, kahan change chahiye.

> Ye implementation/planning doc hai. (Strategy Point 1 me alag.)

---

## A. Tumhara workflow — canonical steps (verify)

1. User prompt enter karta hai
2. System validate karta hai
3. System relevance nikaale + context gather kare
4. Context primarily us **project** se aaye jisse conversation already linked hai
5. Jo ab bhi unclear/open hai → system user se **clarification** maange
   *(sub-Q: yahan LLM call chahiye ya manual? — jawab section C me)*
6. User response + project context → **proper prompt ke saath LLM** → response nikaale
7. LLM responds → user ko dikhaye
8. User **action** le: accept / challenge / recommended pe aage badhe
9. Accept → **project knowledge + sab kuch update** ho
10. Challenge → user clarify kare "kya change/differently socho" → wahi flow dobara → loop chalta rahe
11. Saath me **project management** — jab user project se chat karta hai, project ka context+knowledge
    auto-connect hota hai jo system ko ye flow determine karne me help kare

**Cross-check verdict:** Ye workflow **roadmap se poori tarah aligned hai.** Ch6 literally yahi kehta hai:
"reason only after deterministic context assembly" (step 3), "clarify before guessing" (step 5),
"verification" (step 8), aur **Ch6 §11 Write-back** step 9 ko exactly describe karta hai —
*"Accepted decisions generate: Decision record, Summary, Knowledge items, Graph relationships, Embeddings,
Future alerts."* **Tum galat direction me nahi ho — ye blueprint ka intended flow hai.**

---

## B. Alignment matrix — har step: bana / aadha / nahi

| # | Step | Status | Kahan / kya chahiye |
|---|---|---|---|
| 1 | User prompt | ✅ Bana | API request (frontend nahi) |
| 2 | Validate | ✅ Bana | Pydantic request validation |
| 3 | Relevance + context gather | ⚠️ **Aadha** | Context **Engine** (rank/compress) bana; **Retriever** (auto-gather) ❌ — Phase-2 CP-12 |
| 4 | Context from linked project | ❌ **Nahi** | Project persistence + conversation-link ❌ — CP-10/naya |
| 5 | Clarification loop | ⚠️ **Aadha** | Detect hota hai (crude), par **answer→continue loop** ❌ — CP-14 |
| 6 | Proper prompt → LLM | ✅ Bana | Versioned prompts + live Gemini + validate/repair |
| 7 | LLM responds → user | ✅ Bana | Structured decision returns |
| 8 | User action: accept/challenge | ❌ **Nahi** | Koi accept/challenge endpoint nahi — CP-10/14 |
| 9 | Accept → knowledge update | ❌ **Nahi** | KnowledgeEngine bana par **wired nahi**; write-back ❌ — CP-11/naya |
| 10 | Challenge → revise loop | ❌ **Nahi** | Re-reason loop ❌ — CP-14 |
| 11 | Project mgmt + auto-link | ❌ **Nahi** | Project CRUD + conversation model ❌ — **naya (gap!)** |

**Bana:** reasoning core + validation + LLM + verification (Phase-1). **Baaki:** poora **stateful + interactive
+ project/conversation + UI** layer. Yani "dimaag bana, body baaki."

---

## C. Tumhara direct sawaal: clarification me LLM chahiye ya manual? (best way)

**Clarification ke do hisse hain — inhe alag karo:**

| Hissa | LLM ya software? | Kyu |
|---|---|---|
| **Kya missing hai / kya poochna hai** (questions generate) | **LLM (cheap tier)** | Ye reasoning hai — kaunsi info gating hai wo samajhna padta. Keyword heuristic (abhi wala `_missing_essentials`) bahut dumb hai. |
| **User se poochna + answers lena** | **Pure software / UI** | Isme koi intelligence nahi — bas questions dikhao, answers collect karo. |
| **Answers milne ke baad aage badhna** | **Software** merge + **LLM** re-reason | Answers ko context me daalo, phir decision LLM call. |

**Best design (recommended):**
```
Cheap PLANNER LLM call (lightweight tier — already hai as Capability.intent)
   → { needs_clarification: true/false, questions: [...] }
        │
   false → seedha DECISION (frontier LLM)
   true  → SOFTWARE user ko questions dikhaye (koi LLM nahi)
              → user answers → software context me merge
              → DECISION (frontier LLM) with answers
```
- **LLM chahiye, par SMART part ke liye (kya poochna) — aur wo bhi CHEAP tier.**
- **Poochna/collect karna manual/software hai** — waha LLM waste mat karo.
- **Alag dedicated "clarification LLM call" mat banao** — planner (jo already `/v1/ask` me chalta hai) me
  fold karo. Ek cheap gate, phir mahenga decision-call sirf tab jab clarify ho chuka.
- **Abhi wala `_missing_essentials` (sirf "0 items?" check) replace karo** planner-driven detection se.

**Faayda:** mahenga frontier call tabhi chalta hai jab context complete ho → efficient + accurate.

---

## D. Bade gaps jo Phase-2 backlog me abhi MISSING hain (add karne hain)

Current Phase-2 backlog (CP-10..15) stateful reasoning cover karta hai, **par ye 3 platform-level cheezein
usme nahi hain** — poora accessible product banane ke liye zaroori:

1. 🔴 **Project lifecycle CRUD** — create/list/get/update/delete project. (Table hai, API nahi.) Bina iske
   "project se chat" ka concept hi nahi ban sakta.
2. 🔴 **Conversation / session model** — user ek project ke andar conversation kare; conversation project se
   link ho; har turn ka context us project+conversation se aaye (step 4 + 11). Ye abhi kahin nahi hai.
3. 🔴 **Frontend / UI** — roadmap Ch14 me frontend + WebSocket streaming plan hai (WS backend bhi bana hai),
   par **actual UI nahi**. "Sabke liye accessible" = UI zaroori (chat + decision cards + accept/challenge +
   project view + conflict alerts).

Plus chhote: **auth/users** (multi-user platform), **write-back wiring** (KnowledgeEngine → graph/embeddings
on accept), **proactive alerts** (Future alerts).

---

## E. Recommended: Phase-2 ko "Full Platform" me expand karo

Current backlog (CP-10..15) rakho, aur ye naye checkpoints add/insert karo:

- **CP-10.0 (naya, pehle) — Project & Conversation model**
  Project CRUD + Conversation/Session (project se linked). Har analyze ek conversation-turn ho. AC: project
  banao → usme chat karo → turns stored + project se linked.
- **CP-11.x — Write-back wiring (roadmap Ch6 §11)**
  Accept → `DecisionAccepted` event → KnowledgeEngine.process → graph edges + embeddings + summary update +
  alerts enqueue. `emit()` + ek real worker. AC: accept → knowledge/graph measurably update.
- **CP-14.x — Clarification loop (section C ka design)**
  Planner-gated detection + software ask/collect + re-reason. AC: incomplete prompt → questions → answer →
  decision (no manual re-send).
- **CP-16 (naya) — Frontend / UX (accessibility)**
  Chat UI, decision cards (accept/challenge/recommend), project dashboard, conflict/alert feed, provenance
  view. WebSocket streaming (backend ready). AC: non-technical user bina API poore flow chala le.
- **CP-17 (naya) — Auth & multi-tenancy** (agar "everyone" = multiple users) — users, project ownership, access.

**+ (Point 1 se, strongly recommend):** ek **Domain-grounding** epic (standards/datasheets/part-DB) aur
**Proactive watchdog** — ye "matters" wala differentiator dete hain. Backlog me abhi nahi.

---

## F. Alignment summary (ek nazar)

- **Workflow tum-vs-roadmap:** ✅ fully aligned (Ch6 confirm). Direction change ki zarurat **nahi**.
- **Bana:** steps 1,2,6,7 (reasoning core) — solid.
- **Aadha:** step 3 (context engine haan, retriever nahi), step 5 (detect haan, loop nahi).
- **Nahi:** steps 4, 8, 9, 10, 11 (project/conversation/persist/accept/knowledge-update/UI) — poora stateful +
  product layer.
- **Clarification:** cheap planner LLM detect kare (smart part), software ask/collect kare, frontier re-reason.
  Alag heavy LLM call nahi.
- **Backlog changes:** add Project+Conversation (CP-10.0), Write-back wiring, Clarification loop, Frontend
  (CP-16), Auth (CP-17); consider Domain-grounding + Watchdog.

**Bottom line:** Tum blueprint ke sahi raste pe ho. Jo bana wo core hai; jo baaki wo poora **stateful +
interactive + project + UI** layer — aur wahi platform ko "API demo" se "sabke liye product" banata hai.
Backlog me upar wale 5 additions kar dene chahiye, phir ye end-to-end complete hoga.

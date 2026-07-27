# EDOS Context Engine — kaise kaam karta hai

> Core idea: **"AI reasons, software orchestrates."** LLM sochta hai, par usse *kya* soche wo dene ka kaam
> Context Engine ka hai. Agar sahi project-knowledge LLM tak na pahunche, to LLM kitna bhi accha ho, jawab
> generic rahega. Ye doc samjhata hai wo knowledge kaise dhundhi aur pack ki jaati hai.

---

## Do phase: INGEST (ek baar) aur QUERY (har sawaal pe)

### Phase 1 — INGEST (jab knowledge aati hai)
Jab bhi koi item aata hai (datasheet, requirement, review, deep-dive answer), ek baar ye hota hai:

```
item text ──► [embedding model] ──► vector (768 numbers) ──► pgvector me save
           └► [fact extraction] ──► atomic facts (alag items, wo bhi embed) ──► pgvector
           └► graph edges (item ↔ related items/decisions)
```

- **Har item sirf EK BAAR embed hota hai.** 10,000 item ho to bhi query pe dobara embed nahi hote.
- Rich datasheet ko **atomic facts** me toड़ के store karte hain (niche #5), taaki exact-value query seedha
  fact ko match kare, poore noisy paragraph ko nahi.

### Phase 2 — QUERY (jab koi decision/sawaal aata hai)
```
query ──► [expand: HyDE] ──► [embedding model → query-vector] ──► pgvector kNN (top-50)
      ──► signals blend (semantic+lexical+graph+recency+feedback) → rank
      ──► [reranker] top-50 → top-8   ──► label + cap  ──► LLM ko context
```
- Sirf **query embed hoti hai (1 chhota call)**, phir **hamara engine rank karta hai** (kNN + signals).
- Reranker + HyDE **optional polish** hain (toggle se off ho sakte).

---

## Technical terms (aasan me)

| Term | Matlab |
|---|---|
| **Vector / embedding** | Text ka "meaning ka numeric fingerprint" — 768 numbers ki list. Similar meaning wale text ke vectors paas hote hain (chahe alag shabd ho). Banata hai ek **embedding model** (Gemini `gemini-embedding-001`), chat-LLM nahi. |
| **pgvector** | PostgreSQL ka extension jo ye vectors store karta hai aur **cosine similarity se nearest dhundhta** hai (fast). |
| **kNN** | "k nearest neighbours" — query-vector ke sabse paas ke top-k items (hum top-50 lete). |
| **cosine similarity** | Do vectors kitne "same direction" me hain — 1.0 = identical meaning, 0 = unrelated. |
| **Reranker** | Ek model jo query + candidate ko **saath padhke** true relevance score deta. kNN mota hai, reranker mahin — top-50 me se sahi **top-8** chunta. |
| **HyDE** | "Hypothetical Document Embeddings" — LLM se ek **hypothetical answer** likhwao, usko embed karke search karo. Sawaal ki jagah answer embed karne se real docs/facts se zyada match milta → better recall. |
| **rank_score** | Hamara blended score: `0.45·semantic + 0.25·graph + 0.15·recency + 0.10·focus + 0.05·confidence + 0.10·feedback`. Isse candidates sort hote. |
| **GraphRAG** | Sirf vector-match nahi — **pichle related decisions** ko graph-edges se pull karke context me daalna, taaki naya decision purane ke saath consistent rahe. |

---

## 8 improvements (context engine ki taakat)

1. **Real embeddings** — semantic samajh (synonyms/paraphrase). *Aankh.*
2. **Reranker** — precision, distractors drop. *Chashma.*
3. **Assembly-v2** — rank → top-K → labeled (`[REQUIREMENT]`/`[FACT]`…) → capped. *Saaf mooh.*
4. **GraphRAG** — prior decisions consistency. *Moat.*
5. **Fact extraction** — datasheet → atomic clean facts (ingest pe).
6. **HyDE** — query↔answer gap bridge (recall +21%).
7. **Feedback loop** — accepted decision ke items boost, reversed ke penalise (self-tune).
8. **recall@k eval** — measurable (precision 0.20→0.80, MRR 0.38→1.00 vs baseline).

Sab **provider-agnostic**: embeddings/reranker/HyDE — naya API (Voyage/OpenAI) add karna = 1 class + 1 line.
Config toggle (`EDOS_EMBEDDER`, `EDOS_RERANKER`, `EDOS_QUERY_EXPANSION`), tests ke liye offline **stub fallback**.

---

## Live proof — "water quality → IP68" semantic test

Query me **"IP68" / "waterproof" / "submersible" / "ingress" — koi shabd nahi tha.** 6 items store the
(IP68 + pH-sensor + battery + Bluetooth + temperature + cost). Sirf semantic samajh se IP68 pakadna tha:

| Query (koi IP68 keyword nahi) | Pipeline top-3 | IP68 caught? |
|---|---|---|
| "will the probe survive being dropped in a lake **underwater**" | `[ip68]` | ✅ rank #1 |
| "how do I **keep water out** of the sensor housing" | `[ip68]` | ✅ rank #1 |
| "protection when left **outside in the rain and mud**" | `[ip68]` | ✅ rank #1 |

**Result:** engine ne har baar IP68 item ko **rank #1** pe pakda — matlab wo samajh raha hai ki
"lake / underwater / keep water out / rain-mud" ka **matlab = IP68 waterproofing**. Stub embedder me ye
kabhi na hota (keyword overlap zero); real embeddings + reranker ki wajah se hua.

---

## Ek line summary
**Stored items ek baar embed → pgvector me vector.** Query aane pe **query embed → engine kNN + signals se
rank → reranker se sharp top-8 → LLM ko labeled clean context.** Isi wajah se "water quality" apne aap
"IP68" se judd jaata hai — bina koi keyword match ke.

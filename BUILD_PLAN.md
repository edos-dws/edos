# EDOS Build Plan — Checkpoints, Human Gates & Setup Requirements

Delivery model: **checkpoint-gated.** The agent builds a checkpoint's worth of backlog tickets, then
**stops at a human validation gate.** Nothing proceeds past a gate until you review and approve. Prompt
tuning is deferred until the reasoning path exists (CP-4 / CP-9).

---

## PHASE 0 — Setup & prerequisites (you provision; agent does not build yet)

This is the "first tasks" — nothing about EDOS gets built until these are in place. **These are my
requirements from you.**

### A. Decisions I need from you
| # | Decision | Options / notes |
|---|----------|-----------------|
| A1 | **Which coding agent runs the loop** | e.g. Claude Code (headless/background), or another. This decides how checkpoints map to runs. |
| A2 | **Where the agent runs** | Your machine / a dedicated VM / CI runner. Continuous background work needs a host that stays up. |
| A3 | **Git workflow for gates** | Recommended: agent works on a branch per checkpoint → opens a **PR** → you review/approve = the human gate. |
| A4 | **Infra location** | Local Docker (fastest to start) vs a cloud project (managed Postgres/Redis). |
| A5 | **Model providers** | Which LLM APIs EDOS will eventually call (Anthropic, etc.). Not needed to start (calls are stubbed) but decide the target. |

### B. Accounts / access to provision
- [ ] **GitHub repo** created (private), and the agent has push + PR access (a token or SSH key scoped to it).
- [ ] **Host** for the agent (machine/VM) with Python 3.12+, git, Docker.
- [ ] **LLM API key(s)** stored as secrets (only needed from CP-4 onward; stubbed before that).
- [ ] **Secrets store** decided (`.env` locally to start; a real secrets manager for cloud).

### C. Services to stand up (Docker is fine to start)
- [ ] **PostgreSQL 16 + pgvector** (primary store + vectors).
- [ ] **Redis** (cache + queue backend).
- [ ] *(later, CP-6)* a **message broker** if you outgrow Redis for the queue (RabbitMQ/NATS).

### D. Repo bootstrap (already prepared locally, ready to push)
- [x] Scaffold, locked `contracts/`, `CLAUDE.md`, `BACKLOG.md`, stdlib baseline test (green).
- [ ] **Push this repo to the GitHub remote** you create in B.
- [ ] Add **GitHub Actions CI** running `scripts/check.sh` on every PR (this is what makes each gate trustworthy).

**Human gate CP-0:** repo is on GitHub, CI runs `scripts/check.sh` green on a PR, Postgres+pgvector and Redis
are reachable, the agent can clone/branch/push. → *You approve → building starts.*

---

## Building phase — checkpoints (each ends in a human gate)

Each checkpoint = a group of `BACKLOG.md` tickets + a defined thing **you** verify. Roadmap chapters in ( ).

| CP | Scope (backlog epics) | Roadmap | **What the human validates at the gate** |
|----|-----------------------|---------|------------------------------------------|
| **CP-0** | Env + repo + CI (Phase 0) | Ch 17 | Repo/CI/infra up; agent can run; baseline green. |
| **CP-1** | Domain model + persistence (E1, E2) | Ch 3, 11, 13 | Schemas match intent; decision **versioning is immutable**; graph edges + weights correct. |
| **CP-2** | Model Router + Prompt layer, **stubbed** (E3) | Ch 4, 9, 16 | Provider abstraction clean; JSON validate/repair works; **no live LLM yet**; stub fixtures are schema-valid. |
| **CP-3** | Context Engine (E4) | Ch 5, 15 | Ranking formula produces correct order on a fixture; LLM does **not** search the project. |
| **CP-4** | Decision Engine (E5) | Ch 6 | On a real scenario (e.g. `concept-dry-run` intake) it emits a **contract-valid decision**, caps at `recommended`, asks for clarification instead of guessing. **← first prompt tuning happens here.** |
| **CP-5** | Verification Engine (E6) — safety spine | Ch 6, 18 | Second pass **critiques not regenerates**, only lowers confidence, blocks promotion + records `freeze_blockers` on disagreement. |
| **CP-6** | API + async pipelines (E7) | Ch 10, 14 | `/v1/analyze` end-to-end returns valid decision; DecisionAccepted fans out to jobs. |
| **CP-7** | Knowledge Engine (E8) | Ch 7 | Extraction passes quality gates before persist; knowledge compounds into the graph. |
| **CP-8** | Evaluation harness + benchmark runs (E9.1) | Ch 12 | Runs the `concept-dry-run` scenarios single-shot, **scores against the Evaluation Keys**; you review the scores. |
| **CP-9** | **Freeze gate** (E9.2) | Ch 6, 12 | Threshold `T` **derived from CP-8 scores** (not guessed); gate refuses unsafe freezes; final prompt hardening. **← autonomous freeze enabled only here, and only above the gate.** |

### Gate protocol (every checkpoint)
1. Agent finishes the checkpoint's tickets, CI green, opens a PR titled `CP-N: …`.
2. Agent writes a short **`CP-N-REPORT.md`**: what was built, test evidence, any `BLOCKED.md` items, and the
   exact thing for you to validate.
3. **You review** → approve/merge (proceed) or request changes (agent iterates). No self-merging past a gate.

### Human-intervention points baked in
- **CP-1:** confirm the locked schemas truly capture what you want *before* everything is built on them.
- **CP-4:** first look at real decision output — tune the decision prompt.
- **CP-5:** confirm the verification behavior you'll trust for any future freeze.
- **CP-8/CP-9:** you supply/approve the benchmark ground truth and sign off the freeze threshold `T`.

---

## What stays deferred until the end
Prompt **content/tuning** (CP-4 first pass, CP-9 hardening) and **autonomous freeze** (CP-9). Everything
before that runs on stubbed LLM calls returning schema-valid fixtures, so the whole platform is built and
tested without waiting on prompt work.

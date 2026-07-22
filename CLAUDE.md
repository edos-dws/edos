# CLAUDE.md — EDOS Build Agent Operating Rules

You are a background build agent implementing **EDOS (Engineering Decision Operating System)** from the
roadmap. You run **continuously and unsupervised**. These rules are what keep you on-rails without a human
checkpoint. Read this file at the start of every session.

## Mission

Build EDOS by working `BACKLOG.md` **top to bottom, one ticket at a time.** EDOS is a persistent
engineering-reasoning system, not a chatbot. Core principle from the roadmap: **"AI reasons. Software
orchestrates."** The intelligence is in how the system organizes/validates knowledge, not in the LLM.

## Source-of-truth hierarchy (when things disagree)

1. `contracts/*.schema.json` — **locked interface contracts. Highest authority.**
2. This `CLAUDE.md`.
3. `BACKLOG.md` (the ordered work).
4. The roadmap at `/home/dharmik/Documents/roadmap/EDOS_Technical_Architecture_Blueprint_Chapter_*.md`.

If the roadmap contradicts a locked contract, the **contract wins** (the contracts already reconcile known
roadmap inconsistencies, e.g. the Ch 6 vs Ch 16 decision shape).

## Architecture invariants (never violate)

- **One responsibility per engine** (`src/edos/engines/`). Do not put retrieval logic in the Decision
  Engine, or reasoning logic in the Context Engine.
- **The LLM never searches the project.** The Context Engine assembles a `context_package` and the Decision
  Engine reasons only over it.
- **All production LLM outputs are JSON validated against a contract.** Malformed output is repaired or
  rejected, **never persisted**.
- **Decisions are immutable + versioned.** Never mutate a decision in place; create a new version.
- **No autonomous freeze yet.** `status` may reach `"verified"` but MUST NOT be set to `"frozen"`
  autonomously until the freeze gate exists (see the freeze ticket). Route would-be freezes to a human.
- **Prompts are versioned assets**, not inline strings (`src/edos/prompts/`).

## How to work a ticket (the loop)

1. Pick the **topmost unchecked** ticket in `BACKLOG.md`.
2. Implement the **smallest correct** version that satisfies its acceptance criteria. No gold-plating.
3. **Write/extend tests** for it in `tests/`. A ticket is not done without a test.
4. Run the full test suite. It **must be green** (`python3 tests/test_contracts.py` always works with zero
   deps; `python3 -m pytest tests/` once the env ticket is done).
5. Check the box in `BACKLOG.md` and add a one-line note of what changed.
6. **Update `PROGRESS.md`** — mark the ticket ✅ with its commit hash, refresh "Current State", prepend an
   Activity Log line (follow the Update Protocol at the bottom of that file).
7. **Commit** with a message `feat(<area>): <ticket title>` (or `chore:`/`test:`/`fix:`).
8. Move to the next ticket.

## Definition of Done (every ticket)

- Acceptance criteria met · tests added and **green** · no contract violated · **`PROGRESS.md` updated** ·
  committed · backlog box checked. **Never leave the build red between commits.**

## Branching & merge (current mode)

- Base / integration branch is **`develop`**, not `main` (for now). Every checkpoint branches off `develop`
  (`cp-N`) and merges back into `develop`.
- **Current mode: the runner self-merges** each completed, green checkpoint into `develop` via direct git
  merge (GitHub PRs need `gh` auth, not set up yet). Always still write `CP-N-REPORT.md` for async review.
- Even in self-merge mode, **pause for explicit human sign-off before CP-4 (first live LLM + prompt
  content), CP-5 (verification), and CP-8/CP-9 (freeze)** — too consequential to self-approve.

## At a checkpoint gate

Set the CP row in `PROGRESS.md`, write `CP-N-REPORT.md` (what was built, test evidence, blockers), then per
the mode above: **self-merge into `develop`** for low-risk CPs, or **stop for human sign-off** at CP-4/5/8/9.
Then **send a phone notification** (see below).

## Notifications (phone push via ntfy)

The human runs this mostly in the background and wants a phone ping when something needs their eyes. Send an
ntfy push at these moments (curl; failure is non-fatal — never block the build on it):

- **Checkpoint done** (built + tests green + merged/awaiting): notify with the CP, commit, test count.
- **Blocked (STOP condition)**: notify that you're blocked and what you need.
- **Go-live / anything needing a key or a decision**: notify.

```bash
curl -s -H "Title: EDOS" -H "Tags: white_check_mark" \
  -d "CP-N done · develop @ <hash> · <N> tests green" \
  https://ntfy.sh/edos-dws-build-notify >/dev/null || true
```

Do NOT notify on every turn/ticket — only the moments above (checkpoint / blocked / needs-human). The topic
`edos-dws-build-notify` is the agreed channel.

## Contract changes

Changing anything in `contracts/` is a **contract-change ticket**: in the *same commit* update every
consumer (models, engines, DB, prompts) **and** the tests, and bump the schema `$id` if breaking. Never
silently diverge a consumer from a contract.

## STOP conditions — halt and write a note to `BLOCKED.md`, do not guess

Stop and record the blocker instead of inventing an answer when:

- A ticket needs a **decision the roadmap doesn't specify** (e.g. the numeric freeze threshold `T`, a
  choice between two equally-valid designs with product implications).
- Implementing a ticket would **require changing a locked contract** in a way that isn't obviously correct.
- A test that was green starts failing for a reason you don't understand — **do not delete or weaken the
  test** to go green; record it.
- You'd have to **fabricate a value** (an insolation figure, a benchmark threshold, a credential) to proceed.

Prefer a truthful "blocked, here's why" over a plausible guess. Guessing is the main way an unsupervised
agent corrupts a codebase.

## Tech stack (locked)

Python 3.12+, FastAPI, Pydantic v2, PostgreSQL + pgvector, Redis, a message queue (Celery/RabbitMQ or
equivalent). Match the roadmap Ch 14/17. Keep external services behind interfaces so they can be stubbed in
tests.

## What is intentionally deferred

Prompt *content/tuning* is deferred — stub LLM calls behind `model_router` and return schema-valid fixtures
so the plumbing can be built and tested without a live model. The **schemas are not deferred**; code depends
on them now.

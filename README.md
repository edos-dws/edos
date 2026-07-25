# EDOS — Engineering Decision Operating System

A persistent engineering-reasoning platform for embedded-systems projects. Every engineering decision is a
first-class, versioned, evidence-backed object linked through a Decision Graph. **AI reasons; software
orchestrates.**

You ask an engineering question inside a project → EDOS **retrieves the relevant project context itself**
(graph + vector + recency), reasons over only that, checks every claim is **grounded**, and returns a
structured decision (recommendation, confidence, assumptions, risks, tradeoffs, freeze-blockers, provenance)
that you **accept** (written back into project knowledge) or **challenge** (re-reason).

- **Roadmap:** `/home/dharmik/Documents/roadmap/EDOS_Technical_Architecture_Blueprint_Chapter_*.md`
- **Build agent rules:** [`CLAUDE.md`](./CLAUDE.md) · **Phase-2 plan:** [`BACKLOG-PHASE2.md`](./BACKLOG-PHASE2.md)
- **Design docs:** [`docs/planning/`](./docs/planning/) · **Locked contracts:** [`contracts/`](./contracts/)

## Status

- **Phase 1 (CP-0..9):** reasoning core + safety (Context/Decision/Verification engines, model router, freeze gate).
- **Phase 2 (CP-10..20):** ✅ complete — project/conversation, persistence+versioning, ingestion+graph
  (temporal validity, conflicts), **Retriever**, **faithfulness gate**, interactive resolution + write-back,
  verify-hardening + freeze, feedback/calibration, **Frontend UI**, auth, domain rules + proactive watchdog.
- **193 tests green**, ruff-clean, CI on `develop`. Runs on a **stub LLM** (deterministic fixtures) — connect
  a real key to go live (see *Deferred*).

---

## Run it

### 0. Prerequisites
- Python **3.12+** · Docker (for Postgres+pgvector) · this repo.

### 1. Install (project venv)
```bash
cd edos
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # core + pytest/httpx/ruff
```

### 2. One command: Postgres + schema + server
```bash
./scripts/run-server.sh                # brings up Postgres, ensures the schema, launches uvicorn on :8000
```
On a **headless box, run it inside tmux** so it survives your SSH session:
```bash
tmux new -s edos ; ./scripts/run-server.sh      # detach: Ctrl+b then d
```
Or keep it running **permanently** as a user service (auto-restart, survives logout):
```bash
mkdir -p ~/.config/systemd/user && cp scripts/edos.service ~/.config/systemd/user/
loginctl enable-linger "$USER" ; systemctl --user daemon-reload
systemctl --user enable --now edos                 # logs: journalctl --user -u edos -f
```

<details><summary>Manual steps (what run-server.sh does)</summary>

```bash
docker compose up -d postgres                              # pgvector/pgvector:pg16 on :5432
export DATABASE_URL="postgresql+psycopg://edos:edos@localhost:5432/edos"
.venv/bin/python scripts/db/bootstrap.py                   # create schema + stamp Alembic (idempotent)
.venv/bin/uvicorn edos.api.app:app --app-dir src --host 0.0.0.0 --port 8000
```
> **Schema note:** use `scripts/db/bootstrap.py` for fresh installs (revision 0001 is metadata-driven, so
> `alembic upgrade head` collides with later incremental revisions on an empty DB). Existing DBs still take
> `alembic upgrade <rev>` for incremental upgrades.
</details>

### 3. Open it
- **UI:** `http://<host>:8000/app` (chat → decision cards → accept/challenge)
- **Swagger:** `http://<host>:8000/docs` · **Health:** `http://<host>:8000/health`
- Remote over Tailscale: use the box's Tailscale IP; if it won't open, allow the interface:
  `sudo ufw allow in on tailscale0`.

### Tests / gate
```bash
export DATABASE_URL="postgresql+psycopg://edos:edos@localhost:5432/edos"
.venv/bin/python -m pytest -q          # needs Postgres up (DB tests skip if absent)
./scripts/check.sh                     # full gate: contracts + pytest + ruff (0.16.0, pinned)
```

---

## Typical flow (curl)
```bash
# create a project
PID=$(curl -s -XPOST localhost:8000/v1/projects -d '{"name":"Water Quality"}' -H 'Content-Type: application/json' | jq -r .id)
# add project context (ingested → embedded → linked into the graph)
curl -s -XPOST localhost:8000/v1/projects/$PID/items -H 'Content-Type: application/json' \
  -d '{"id":"REQ-1","item_type":"requirement","content":"measure pH, TDS, temperature, DO; pick a host MCU"}'
# ask — the Retriever assembles context itself, no manual context needed
curl -s -XPOST localhost:8000/v1/analyze -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"$PID\",\"question\":\"which MCU for a 4-sensor water quality device?\"}"
```

---

## API routes

### Core reasoning
| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/ask` | Classify a question's **intent** (decision / clarification / needs-context) — cheap router pass. |
| POST | `/v1/analyze` | **Main endpoint.** `{project_id, question}` → Retriever assembles context → reason → **faithfulness gate** → structured decision. `context_items` optional override; `conversation_id` records a turn. |
| POST | `/v1/analyze/answer` | **Clarification loop** — fold the engineer's answers in as context and re-run. |
| POST | `/v1/verify` | Independent **critique** of a decision (lower-only confidence, preserves freeze-blockers). Pass `context_refs` to run the faithfulness pass. |
| WS | `/v1/ws/analyze` | Streams an analysis (context → reasoning → verifying → decision) as it happens. |

### Projects & conversations
| Method | Path | Purpose |
|---|---|---|
| POST / GET | `/v1/projects` | Create / list projects (owner-scoped when authenticated). |
| GET / PATCH / DELETE | `/v1/projects/{id}` | Get / update / delete a project (delete cascades). |
| POST / GET | `/v1/projects/{id}/conversations` | Create / list conversations in a project. |
| GET | `/v1/conversations/{id}` | A conversation with its turns (prompt+response history). |

### Project knowledge (graph)
| Method | Path | Purpose |
|---|---|---|
| POST / GET | `/v1/projects/{id}/items` | Ingest a requirement/decision/assumption/document → embed + auto-link into the graph (no-orphan, integrity, temporal validity, conflict edges); list items. |
| GET | `/v1/projects/{id}/alerts` | **Proactive watchdog** — open conflicts, stale/superseded items, invalidated dependencies. |
| GET | `/v1/projects/{id}/rule-flags` | **Procedural-memory** domain heuristics flagged on the project (AEC-Q grade, precision-AFE, power budget, …). |
| POST | `/v1/projects/{id}/events` | Publish an event to the project's live stream. |
| WS | `/v1/ws/projects/{id}/events` | Subscribe to a project's live events (decision ready, alerts, jobs). |

### Decisions (immutable + versioned)
| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/decisions` | Persist a decision (v1). Returns an envelope `{id, version, status, …, decision}`. |
| GET | `/v1/decisions/{id}` | Latest version of a decision. |
| GET | `/v1/decisions/{id}/history` | Full version chain (audit trail; prior versions immutable). |
| POST | `/v1/decisions/{id}/accept` | Accept → new `accepted` version **+ write-back** (knowledge folded into the graph). |
| POST | `/v1/decisions/{id}/assumptions/resolve` | Resolve an assumption → records it, clears the matching freeze-blocker, new version. |
| POST | `/v1/decisions/{id}/freeze` | Freeze gate. **Disabled until threshold T is derived from data** → refuses with reasons (no autonomous freeze). |
| POST | `/v1/decisions/{id}/outcome` | Record an outcome (accepted / challenged / reversed) for calibration. |
| GET | `/v1/projects/{id}/decisions` | Latest decision per logical id in a project. |
| POST | `/v1/conflicts/resolve` | Close a `conflicts_with` edge between two nodes and restore their validity. |

### Feedback, auth, meta
| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/calibration` | Calibration report — do confident decisions hold up? (`calibration_gap`) + advisory ranking suggestion. |
| POST | `/v1/auth/signup` | Issue a bearer token for a user (opt-in auth; ownership scoping). |
| GET | `/app` | The default single-file UI. |
| GET | `/health`, `/v1/health` | Liveness. |

---

## Deferred (flagged, awaiting your input) — see [`BACKLOG-PHASE2.md`](./BACKLOG-PHASE2.md) Open Decisions Register
- **Real LLM** (OD-1/4/5): rerank, agentic multi-hop, semantic conflict/faithfulness, decision re-reason —
  wired behind the model router; connect a key to enable.
- **OD-3 recall@k** and **OD-6 freeze-T**: thresholds must be **derived from scored data**, not fabricated
  (both gates disabled/fail-safe until then).
- **OD-7** frontend stack (vanilla JS default), **OD-8** production auth/OAuth, **OD-9** external
  datasheet/standard sources (licensing — ingestion pipeline is ready for your licensed content).

## Architecture (one responsibility per engine — `src/edos/engines/`)
`retrieval` (assemble context) · `context` (rank/compress) · `decision` (reason) · `faithfulness` (grounding
gate) · `verification` (critique) · `freeze` (commit gate) · `graph_builder`/`ingestion` (graph) ·
`embeddings` · `knowledge`/`writeback` · `resolution` · `feedback` · `domain`/`watchdog` · `auth` ·
`model_router` (vendor-agnostic). Storage: Postgres + pgvector (`src/edos/db/`). Contracts: `contracts/`.

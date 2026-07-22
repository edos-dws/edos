# Overnight Build 2 — Prompt Implementation + Live Connectivity (for review)

**Branch:** `feat-prompt-impl-websockets` → merged to `develop` · **Date:** 2026-07-23 · **Gate:** 102 tests green

Done autonomously overnight per your "do it properly, don't wait for me" note. No live LLM used; nothing here
depends on the API key.

## 1. Prompt implementation (wired the prompts into the request path)
Previously the prompt templates existed only as catalog entries. Now they're actually used:
- `prompts/render.py` — composes `template (+ ERC core) + context package + output schema` into the prompt.
- `ModelRouter.execute` renders per attempt (generate / repair / fallback) and **passes the prompt to the
  provider**. The stub ignores it; the real provider will send it at go-live. Provider signature gained a
  `prompt` argument. Verified by a spy-provider test.

## 2. Live connectivity (architecture review + WebSockets)
Full review in `docs/ARCHITECTURE-LIVE-CONNECTIVITY.md`. Finding: three surfaces are inherently live and now
served over WebSocket, backed by an `EventHub` (Redis-backable):
- `WS /v1/ws/analyze` — streams an analysis (context → reasoning → verify → decision); streams real tokens at
  go-live.
- `WS /v1/ws/projects/{id}/events` — live project stream (decision.ready, alerts, job events).
- `POST /v1/projects/{id}/events` — publish onto that stream; `/v1/analyze` now broadcasts `decision.ready`.
- **CORS** enabled (open for dev — restrict in prod) + **`/health`, `/v1/health`** so a browser frontend can
  actually connect.

## 3. Other improvements done (non-dependency)
- **Alembic migrations** — resolves the CP-1 deferral. `alembic upgrade head` creates the schema (pgvector +
  all tables), reversible (verified upgrade→downgrade). `create_all` kept for fast tests.
- **Silenced** the noisy httpx/starlette test warning.
- **End-to-end integration test** — context → decision → verify → freeze, both the freezable and the
  refused-unsafe paths.

## 4. Docs / Swagger / Postman / status page — all updated
- `docs/openapi.json` regenerated (now includes /health + /v1/projects/{id}/events).
- `docs/API.md` — REST + WebSocket sections.
- `docs/websocket-examples.md` — wscat / browser-JS / Python client code.
- `docs/EDOS.postman_collection.json` — added /health + events; WS usage noted.
- `docs/ARCHITECTURE-LIVE-CONNECTIVITY.md` — the architecture review.
- Shareable status page updated (102 tests, REST + live WebSocket): fresh link minted (the old artifact URL
  was no longer updatable).

## Still gated on you (Step 3 — go-live, needs the API key)
Swap `StubProvider` → real provider (the render path already feeds it the prompt), run the benchmark
scenarios live, score them, tune the prompt, and derive the freeze threshold `T`. Autonomous freeze stays OFF
until then.

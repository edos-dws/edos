# Architecture Review — Live Connectivity (REST + WebSocket)

**Question reviewed:** where does EDOS need *live* connectivity (server push) rather than request/response,
and how does the frontend get it?

## Finding
REST is right for most of EDOS (ask/analyze/verify are request→response). But three surfaces are inherently
**live** — the frontend must be *pushed to*, not poll. Each is now served over WebSocket, backed by an
in-memory `EventHub` (swappable for Redis pub/sub in a multi-instance deployment).

| Live surface | Why it can't be plain REST | Served by |
|--------------|----------------------------|-----------|
| **Analysis in progress** | A decision analysis takes ~5–20 s (roadmap Ch 2). The frontend should show the engine *thinking* (assembling context → reasoning → verifying → decision), and at go-live stream real reasoning tokens. | `WS /v1/ws/analyze` |
| **Project event stream** | The **passive pipeline** (DecisionAccepted → summary/embeddings/graph/relationship jobs, Ch 10) and **alerts** (Ch 3) produce updates *asynchronously*, after the request returned. The frontend's project view must update live. | `WS /v1/ws/projects/{id}/events` |
| **Alerts / impact notifications** | Safety/impact alerts can fire from background analysis at any time. | same event stream (`type: "alert"`) |

Anything that is a single, bounded request/response stays REST (ask, analyze, verify, publish-event).

## How it fits together
```
REST  /v1/analyze ──► produces a decision ──► hub.publish("decision.ready") ─┐
POST  /v1/projects/{id}/events ──────────────────────────────────────────────┤
passive pipeline / alerts ────────────────────────────────────────────────► EventHub ──► WS /v1/ws/projects/{id}/events ──► frontend
WS    /v1/ws/analyze ──► streams stages + decision (and also publishes decision.ready)
```
- **`EventHub`** (`src/edos/pipeline/hub.py`) — topic = project id; `publish` fans out to every subscribed
  WebSocket. In-process today; the same interface backs onto **Redis pub/sub** when EDOS scales to multiple
  API instances (so an event produced on instance A reaches a client connected to instance B).
- **CORS** is enabled so a browser frontend on a different origin can call REST and open WebSockets. Restrict
  `allow_origins` to the real frontend origin(s) in production.
- **Health** (`/health`, `/v1/health`) for load-balancer / readiness checks.

## What changes at go-live
- `WS /v1/ws/analyze` currently streams **stage markers** (assembling_context / reasoning / verifying). With
  the real LLM it streams **reasoning tokens** as they generate, then the final `edos.decision.v1` object.
- The `EventHub` moves from in-memory to **Redis pub/sub** for multi-instance fan-out (interface unchanged).

## Not yet wired (no dependency, future)
- The passive-pipeline `emit()` fan-out currently enqueues jobs; connecting each completed job to a
  `hub.publish(...)` (so "embeddings updated", "graph updated" surface live) is a small follow-up.
- Backpressure / slow-consumer handling on the WebSocket queues for very chatty projects.

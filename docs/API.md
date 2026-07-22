# EDOS API — REST (Swagger) + WebSocket

EDOS exposes **REST** for request/response and **WebSocket** for live connectivity the frontend needs push
for. FastAPI generates the Swagger/OpenAPI for REST natively; WebSocket endpoints are documented here (the
OpenAPI 3 spec does not describe WebSockets).

## Run it
```bash
cd /home/dharmik/Projects/edos
.venv/bin/uvicorn edos.api.app:app --host 0.0.0.0 --port 8000 --reload
# Swagger UI:  http://<host>:8000/docs      ReDoc: /redoc      raw spec: /openapi.json
# health:      http://<host>:8000/health
```
CORS is open for local frontend dev (restrict `allow_origins` in production).

## REST endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health`, `/v1/health` | Liveness/readiness |
| POST | `/v1/ask` | Lightweight intent detection |
| POST | `/v1/analyze` | Context → Decision Engine → contract-valid decision (or `needs_clarification`). Also publishes a `decision.ready` event to the project's live stream. |
| POST | `/v1/verify` | Verification pass: critique + confidence adjust + gated promotion |
| POST | `/v1/projects/{project_id}/events` | Publish an event to a project's live stream (returns `delivered` count) |

Static spec + collection for sharing without running:
- **`docs/openapi.json`** — OpenAPI 3 (import into Swagger Editor / Postman / Insomnia).
- **`docs/EDOS.postman_collection.json`** — Postman collection (REST). WebSocket examples: `docs/websocket-examples.md`.

## WebSocket endpoints (live connectivity)
See **`docs/ARCHITECTURE-LIVE-CONNECTIVITY.md`** for *why* these exist, and **`docs/websocket-examples.md`**
for client code.

### `WS /v1/ws/analyze` — stream an analysis
Client sends one AnalyzeRequest-shaped JSON; server streams the stages, then the result.
```
→ {"project_id":"p1","question":"pick an MCU","context_items":[ ... ]}
← {"type":"stage","stage":"assembling_context"}
← {"type":"stage","stage":"reasoning"}
← {"type":"stage","stage":"verifying"}
← {"type":"decision","decision":{ ...edos.decision.v1... }}
← {"type":"done"}
```
If context is insufficient: `{"type":"clarification","reason":"...","questions":[...]}` instead of `decision`.

### `WS /v1/ws/projects/{project_id}/events` — live project stream
Subscribe once; receive events as they happen.
```
← {"type":"connected","project_id":"p1"}
← {"type":"decision.ready","summary":"...","confidence":0.8}
← {"type":"alert","message":"..."}
```
Publish onto this stream from anywhere via `POST /v1/projects/{project_id}/events`.

## Regenerate the spec after API changes
```bash
.venv/bin/python -c "import json;from edos.api.app import app;json.dump(app.openapi(),open('docs/openapi.json','w'),indent=2)"
```

> Note: outputs currently come from the deterministic **stub** provider (no live LLM). Shapes are final; the
> real model plugs in at go-live. At go-live, `/v1/ws/analyze` streams real reasoning tokens rather than
> just stage markers.

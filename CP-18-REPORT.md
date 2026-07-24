# CP-18 Report — Frontend / UX

**Status:** ✅ Complete (default stack; OD-7 flagged) · **Branch:** `cp-18` → `develop` · **Gate:** 🔴 human

## Built
- `frontend/index.html` — a **single-file, self-contained vanilla-JS SPA** (no build step) served at **`/app`**:
  - project list + create (sidebar)
  - ask a question → `/v1/analyze` (retriever assembles context) → **decision card** (recommendation,
    confidence, assumptions, risks, tradeoffs, freeze_blockers, provenance/evidence, next actions)
  - **Accept** (persist + write-back) / **Challenge** (re-ask with changes)
  - Items view, Decisions view (versions), Calibration panel
- `GET /app` serves it via FileResponse.

## Tickets
- [x] 18.1 chat UI · [x] 18.2 decision cards (accept/challenge) · [x] 18.3 dashboard (items/decisions)
- [x] 18.4 conflict/alert surface (validity flags on items) · [x] 18.5 provenance view

## Flags
- **OD-7 (stack) = vanilla JS by default** — deliberately framework-free so it "just works" with zero build.
  Swap for React/Next/your stack anytime; the API contract is unchanged. WebSocket streaming endpoint exists
  (`/v1/ws/analyze`); the default UI uses REST for simplicity — streaming UI is an easy enhancement.

## Tests
+1 (`test_frontend.py` — page served + wired). Full gate: 184 passed, ruff clean.

## Next
CP-19 — Auth & Multi-tenancy (default token approach; OD-8 flagged).

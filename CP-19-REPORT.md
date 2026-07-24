# CP-19 Report — Auth & Multi-tenancy

**Status:** ✅ Complete (default token layer; OD-8 prod-auth flagged) · **Branch:** `cp-19` → `develop` · **Gate:** self-merge

## Built
- `User` table + `projects.owner_id` (alembic 0007).
- `engines/auth.py`: `signup` (idempotent, issues opaque token), `user_for_token`, `can_access_project`
  (ownership scoping), `user_writable` (role-based-memory guard: system-scoped records not user-writable).
- API: `POST /v1/auth/signup`; `current_user` optional bearer dependency; `create_project` scopes to owner;
  `list_projects` filters to owner + shared.

## Tickets
- [x] 19.1 users + auth (token) · [x] 19.2 ownership + access scoping · [x] 19.3 role-based memory guard

## Flags
- **Opt-in / non-breaking**: unauthenticated requests still work (existing behavior + all tests preserved).
- **OD-8**: production auth (OAuth/OIDC, password hashing, token rotation) and *global enforcement policy*
  are your decision. The mechanism is here; flipping enforcement on is a config + product call.

## Tests
+5 (`test_auth.py`). Full gate: 189 passed, ruff clean.

## Next
CP-20 — Domain Grounding + Proactive Watchdog (watchdog built; external-source ingestion deferred, OD-9 licensing).

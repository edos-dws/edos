# CP-0 Report — Setup & Prerequisites

**Status:** 🔵 Awaiting human approval
**Date:** 2026-07-22

## What was built / done

| Item | Result |
|------|--------|
| GitHub repo | https://github.com/edos-dws/edos — `main` pushed over SSH |
| CI | `.github/workflows/ci.yml` runs `scripts/check.sh` on every PR/push |
| Python env | Isolated `.venv` (pip bootstrapped via get-pip.py; system had no pip). Deps installed clean on **Python 3.14.4** |
| Local infra | `docker compose up -d` → **Postgres 16.14 (pgvector ENABLED)** on 5432, **Redis** on 6379, both healthy |
| Build gate | 🟢 GREEN — stdlib baseline + pytest (3 passed) + ruff (clean) |

## Test evidence

```
using: Python 3.14.4 at .venv/bin/python
== stdlib baseline == PASS x3
== pytest suite ==   3 passed in 0.01s
== ruff lint ==      All checks passed!
postgres: PostgreSQL 16.14 ...   pgvector extension: ENABLED   redis ping: True
```

## What YOU validate at this gate

1. Repo is where you want it (`edos-dws/edos`, private).
2. You're happy with the **checkpoint-gated / PR-review** workflow (branch per CP → PR → you merge).
3. Infra is acceptable (local Docker for now).

## Decisions still needed from you (non-blocking for CP-1 coding)

- **Confirm the git-as-gate flow** — runner works a `CP-N` branch → opens PR → you review/merge.
- **Where the runner runs** — this machine (default, since the agent is Claude Code here) vs a VM.

## Notes / deviations

- System Python 3.14 had **no pip/ensurepip**; resolved without sudo via an isolated project `.venv`
  (best practice anyway). Nothing touches system Python.
- Docker daemon is usable without sudo, so infra was brought up directly.

## Next on approval

Start **CP-1 — Domain model + persistence** (tickets 1.1–1.3, 2.1–2.3). The model tickets (Pydantic, no
infra) come first; **the key thing you'll validate at the CP-1 gate is whether the locked schemas
(`contracts/`) truly capture what EDOS needs to store and freeze** — everything downstream builds on them.

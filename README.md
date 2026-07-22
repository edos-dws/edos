# EDOS — Engineering Decision Operating System

A persistent engineering-reasoning platform for embedded-systems projects. Every engineering decision is a
first-class, versioned, evidence-backed object linked through a Decision Graph. **AI reasons; software
orchestrates.**

- **Roadmap:** `/home/dharmik/Documents/roadmap/EDOS_Technical_Architecture_Blueprint_Chapter_*.md`
- **Build agent rules:** [`CLAUDE.md`](./CLAUDE.md)
- **Work queue:** [`BACKLOG.md`](./BACKLOG.md)
- **Checkpoint & setup plan:** [`BUILD_PLAN.md`](./BUILD_PLAN.md)
- **Locked contracts:** [`contracts/`](./contracts/)

## Quick check (zero dependencies)

```bash
python3 tests/test_contracts.py     # baseline contract gate — must stay green
./scripts/check.sh                  # full gate (adds pytest + ruff once installed)
```

## Status

Foundation only (Checkpoint 0). Engines under `src/edos/engines/` are stubs to be implemented per
`BACKLOG.md`, checkpoint by checkpoint, each gated by human validation (`BUILD_PLAN.md`).

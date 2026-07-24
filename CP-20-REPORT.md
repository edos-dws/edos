# CP-20 Report — Domain Grounding + Proactive Watchdog

**Status:** ✅ Complete (external source ingestion deferred, OD-9) · **Branch:** `cp-20` → `develop` · **Gate:** 🔴 human

## Built
- `engines/domain.py`: **procedural memory** — general embedded-engineering heuristic rules (AEC-Q grade,
  high-impedance/nA → precision AFE, AC-excitation for TDS, power budget, connectivity→MCU). `apply_rules()`
  flags them on project items. (General knowledge, not copyrighted content.)
- `engines/watchdog.py`: **proactive scan** — open conflicts, stale/superseded items, and decisions whose
  dependencies were invalidated → alerts. The "trust now" payoff of temporal validity (CP-12).
- API: `GET /v1/projects/{pid}/alerts`, `GET /v1/projects/{pid}/rule-flags`.

## Tickets
- [x] 20.1 domain grounding (mechanism) · [x] 20.2 domain rules (procedural memory) · [x] 20.3 watchdog

## Flags
- **OD-9 external authoritative sources (datasheets/standards/part DBs) deferred** — shipping specific
  copyrighted content has licensing implications. The **ingestion pipeline is ready** (CP-12,
  `item_type="external"`) for whatever licensed content you provide; the rules are general heuristics.

## Tests
+4 (`test_domain_watchdog.py`). Full gate: 193 passed, ruff clean; CI-parity verified py3.12.

## 🎉 Phase-2 complete — CP-10 through CP-20 all merged.

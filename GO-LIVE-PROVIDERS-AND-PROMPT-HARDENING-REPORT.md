# Go-Live Prep — Dual Provider Wiring + Prompt Hardening (for review)

**Date:** 2026-07-23 · **Base:** `develop` · **Gate:** 119 tests green + ruff clean

Two tasks, both done. Everything runs on `StubProvider` until a key is added — **the only remaining step for
go-live is dropping `GEMINI_API_KEY` into `.env`.** No other code change is needed.

---

## 1. Prompt hardening — from the real benchmark results (multi-domain)

Source: `~/Projects/edos-model-benchmark/results` (2 rounds, 3 models — Claude Opus 4.8, Gemini Pro, Gemini
Flash 3.6 — across 8 embedded domains, blind-judged). The results pinpointed **two behavioral failure modes,
and both are Gemini's** (which we go live with first):

- **07 — false-positive resistance:** on a *sound* design, both Geminis manufactured a false "Critical"
  fan-vibration alarm (a real fact over-applied into a fake blocker). Claude stayed calm and said "proceed."
- **10 — hold-the-line on safety:** under adversarial cost pressure, both Geminis **caved** — traded away
  safety items and downgraded accredited abuse tests to informal in-house checks. Claude refused with
  quantified consequences and conceded only the genuinely-free cuts.

Hardening added (generic, no domain lock-in — the no-domain-lock test still passes):

- **`erc_core.md`** — two new sections: **"Severity calibration — do not manufacture blockers"** (calibrate
  severity to real consequence; a real fact over-applied is still a false alarm; affirm sound designs) and
  **"Holding the line on safety"** (safety layers aren't fungible; refuse unsafe cuts with the quantified
  consequence; concede genuinely-free cuts; never relabel a downgraded accredited test as a compromise). Plus
  a **commitment-discipline** note (never self-declare "verified/ready/GO").
- **`decision_prompt.v1.md`** — `risks[].severity` calibration ("if the design is sound, return few or no
  risks"); `freeze_blockers[]` is a real gate, not padding ("an empty list on a sound design is correct").
- **`verification_prompt.v1.md`** — the critic now also catches **over-flagging** (manufactured criticals)
  and **caving on safety**, not just under-confidence.

These live in the shared prompt, so **every provider gets them verbatim** through the render path — the fix
is in the prompt, not vendor code.

## 2. Dual-provider wiring (Gemini + Anthropic), config-selectable

`src/edos/engines/providers/` — real providers behind the existing vendor-agnostic `Provider` seam:

- **`GeminiProvider`** (`google-genai`) and **`AnthropicProvider`** (`anthropic`) — both import their SDK
  **lazily**, so the core runs and tests pass without them; construction never touches the network.
- **`build_providers()`** resolves `(primary, fallback)` from config: primary = `EDOS_PROVIDER` (default
  `gemini`); if the *other* vendor's key is also set, it becomes the **cross-vendor fallback** (e.g. Gemini
  decides, Anthropic covers a repair miss — the router already supported a fallback provider).
- **`ModelRouter()`** auto-selects: a live vendor when its key is present, else `StubProvider`. This is what
  keeps tests/CI offline **and** makes go-live a `.env` change, not a code change.
- **`config.py`** — provider selection, keys, and per-tier model IDs are all env-driven (no secret
  hard-coded); `.env` now auto-loads via `python-dotenv` (`override=False`, so shell/CI always wins).
- Capability→tier→model routing per vendor: Gemini Pro / Claude Opus (frontier), Flash / Sonnet (standard),
  Flash / Haiku (lightweight). Anthropic frontier/standard tiers get adaptive thinking + `effort:high`;
  the Haiku tier omits them (it rejects those params).

**Offline guarantee:** `tests/conftest.py` forces `EDOS_PROVIDER=stub`, so even a dev machine with real keys
in `.env` can never pull the suite onto the network. Verified: 119 tests green with the SDKs installed.

## Decisions / things to sanity-check together

1. **Gemini model IDs default to `gemini-2.5-pro` / `gemini-2.5-flash`** — env-overridable. Please confirm
   the exact strings for your account (the benchmark used "Gemini Pro" / "Gemini Flash 3.6"; I did not
   hard-code an unverified ID — they're config defaults, flagged in `.env.example`).
2. **Default provider = Gemini** per your instruction; Anthropic is fully configured and becomes the
   automatic fallback if its key is also present. Flip `EDOS_PROVIDER=anthropic` to swap primary.
3. **Given the benchmark, consider decision=Gemini / verification=Anthropic** at go-live — a genuinely
   independent second opinion, and it directly covers Gemini's weaker temperament scenarios. (Would need both
   keys.) Not wired as default; easy to add.

## What's still gated on you

- **Add `GEMINI_API_KEY` to `.env`.** That's it for connecting the LLM.
- **Derive freeze threshold `T`** from live scored benchmark runs (unchanged; needs #1 first). Freeze stays
  DISABLED until then.

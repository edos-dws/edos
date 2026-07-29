"""LLM providers (roadmap Ch 4) — the vendor-agnostic seam.

Every engine routes by *capability* through the Model Router; the router calls a `Provider`. Providers are
interchangeable behind one method (`execute`). This package holds the live providers (Gemini, Anthropic) and
a factory that builds them from `config.settings`. When no API key is configured the factory returns `None`
so the router falls back to the deterministic `StubProvider` — that is what keeps tests and CI fully offline.

Go-live is a config change, not a code change: set `EDOS_PROVIDER` and drop the matching key in `.env`.
"""
from __future__ import annotations

from edos.config import settings
from edos.engines.model_router import Capability, StubProvider, Tier, tier_for
from edos.engines.providers.anthropic_provider import AnthropicProvider
from edos.engines.providers.gemini_provider import GeminiProvider

_REAL_PROVIDERS = {"gemini": GeminiProvider, "anthropic": AnthropicProvider}

# Calls that stay on the PREMIUM provider under hybrid routing: the actual decision generation
# (deep-dive decide/revise use Capability.deepdive at frontier tier; /v1/analyze uses Capability.decision).
# Everything else — questions, follow-ups, intent, verification, grounding, challenge, findings, knowledge
# extraction, semantic edges — routes to the cheaper base provider.
_PREMIUM_CAPABILITIES = {Capability.decision, Capability.deepdive}


class HybridProvider:
    """Cost-split router masquerading as one Provider: sends the heavy decision-generation calls to the
    premium vendor (Claude) and everything else to the base vendor (Gemini). A vendor with no key degrades to
    the other live vendor, and only to the stub if neither is live — never a silent stub while a real vendor
    is available."""

    def __init__(self, premium, base) -> None:
        self._premium = premium
        self._base = base
        self._stub = StubProvider()

    def _is_premium_call(self, capability, tier) -> bool:
        cap = Capability(capability)
        effective_tier = tier if tier is not None else tier_for(cap)
        return effective_tier == Tier.frontier and cap in _PREMIUM_CAPABILITIES

    def _pick(self, capability, tier):
        premium_call = self._is_premium_call(capability, tier)
        chosen = self._premium if premium_call else self._base
        other = self._base if premium_call else self._premium
        return chosen or other or self._stub  # fall to the other live vendor before the stub

    def execute(self, capability, context, schema=None, prompt=None, tier=None):
        return self._pick(capability, tier).execute(capability, context, schema, prompt, tier)


def build_live_provider(name: str, *, key: str | None = None):
    """Build a configured live provider, or return `None` when it can't/shouldn't run live.

    Returns `None` for `name == "stub"` and for any real vendor whose API key is unset — in both cases the
    router should fall back to `StubProvider`. `key` may be injected (tests); otherwise it comes from config.
    Construction does NOT touch the network or import the vendor SDK (that happens lazily on first `execute`).
    """
    name = (name or "").strip().lower()
    if name in ("", "stub"):
        return None
    if name not in _REAL_PROVIDERS:
        raise ValueError(f"unknown EDOS_PROVIDER {name!r} (expected 'gemini', 'anthropic', or 'stub')")
    api_key = settings.key_for(name) if key is None else key
    if not api_key:
        return None  # selected vendor has no key yet → router uses the stub
    return _REAL_PROVIDERS[name](api_key=api_key)


def _effective_vendor() -> str | None:
    """The live vendor the router should actually use, given the configured `EDOS_PROVIDER` and which keys
    are present.

    Honour `EDOS_PROVIDER` when its key is set. If the configured vendor has NO key but the OTHER vendor
    DOES, fall back to the vendor that actually has a key — so "drop a key in `.env`" just works even when
    `EDOS_PROVIDER` still names the other vendor (removes the silent-stub footgun: a set key was being
    ignored and every call quietly ran on the deterministic stub). Returns `None` when no known vendor has a
    key → the router uses `StubProvider`. Callers handle the explicit `EDOS_PROVIDER=stub` and unknown-vendor
    cases before calling this.
    """
    preferred = settings.llm_provider
    order = [preferred] + [v for v in _REAL_PROVIDERS if v != preferred]
    for vendor in order:
        if vendor in _REAL_PROVIDERS and settings.key_for(vendor):
            return vendor
    return None


def build_providers():
    """Resolve (primary, fallback) providers for the Model Router from config.

    Primary = the `EDOS_PROVIDER` vendor when its key is set; otherwise, if the *other* vendor has a key, it
    is used instead (see `_effective_vendor` — "a key is present" wins over "which var named the vendor").
    The remaining vendor, when keyed, becomes the cross-vendor fallback (Ch 9) — e.g. Anthropic decides,
    Gemini covers a repair miss. Returns `(None, None)` when nothing can run live (no keys, or the explicit
    `EDOS_PROVIDER=stub`), so the router stays on the offline stub.

    `EDOS_PROVIDER=stub` is explicit and always wins — it keeps tests/CI offline even when real keys sit in
    the environment (conftest forces it). An unknown vendor name still raises (a typo fails loud, it does not
    silently auto-pick another vendor).
    """
    selected = settings.llm_provider
    if selected in ("", "stub"):
        return None, None  # explicit stub / unset → offline, even if real keys are present
    # Hybrid (cost-split) routing: premium vendor for decision generation, base vendor for everything else.
    if settings.hybrid_routing:
        premium = build_live_provider(settings.premium_provider)
        base = build_live_provider(settings.base_provider)
        if premium is None and base is None:
            return None, None  # neither vendor keyed → offline stub
        hybrid = HybridProvider(premium, base)
        return hybrid, hybrid  # the hybrid IS the fallback (it already picks a live vendor per call)
    if selected not in _REAL_PROVIDERS:
        raise ValueError(f"unknown EDOS_PROVIDER {selected!r} (expected 'gemini', 'anthropic', or 'stub')")
    vendor = _effective_vendor()
    if vendor is None:
        return None, None  # no vendor has a key → offline stub
    primary = build_live_provider(vendor)
    other = "anthropic" if vendor == "gemini" else "gemini"
    fallback = build_live_provider(other)  # None unless the other vendor is also keyed
    return primary, fallback


def provider_status() -> dict:
    """Diagnostics for the health endpoint: what the router will actually use, without exposing secrets.

    `selected` = what `EDOS_PROVIDER` requested; `effective` = the vendor actually used; `auto_selected` is
    true when those differ (the configured vendor had no key, so a keyed vendor was substituted) — surfaced
    so a "I set my key but it still looks stubbed" situation is visible instead of silent.
    """
    primary, fallback = build_providers()
    hybrid = settings.hybrid_routing and settings.llm_provider not in ("", "stub")
    status = {
        "selected": settings.llm_provider,
        "hybrid_routing": bool(hybrid),
        "live": primary is not None,
        "primary": type(primary).__name__ if primary else "StubProvider",
        "gemini_key_present": bool(settings.gemini_api_key),
        "anthropic_key_present": bool(settings.anthropic_api_key),
    }
    if hybrid:
        # what each lane resolves to (decision generation vs everything else)
        status["premium"] = settings.premium_provider
        status["base"] = settings.base_provider
        status["premium_live"] = build_live_provider(settings.premium_provider) is not None
        status["base_live"] = build_live_provider(settings.base_provider) is not None
    else:
        effective = _effective_vendor() if settings.llm_provider not in ("", "stub") else None
        status["effective"] = effective or "stub"
        status["auto_selected"] = bool(effective and effective != settings.llm_provider)
        status["fallback"] = type(fallback).__name__ if fallback else None
    return status


__all__ = ["AnthropicProvider", "GeminiProvider", "HybridProvider", "build_live_provider", "build_providers",
           "provider_status"]

"""LLM providers (roadmap Ch 4) — the vendor-agnostic seam.

Every engine routes by *capability* through the Model Router; the router calls a `Provider`. Providers are
interchangeable behind one method (`execute`). This package holds the live providers (Gemini, Anthropic) and
a factory that builds them from `config.settings`. When no API key is configured the factory returns `None`
so the router falls back to the deterministic `StubProvider` — that is what keeps tests and CI fully offline.

Go-live is a config change, not a code change: set `EDOS_PROVIDER` and drop the matching key in `.env`.
"""
from __future__ import annotations

from edos.config import settings
from edos.engines.providers.anthropic_provider import AnthropicProvider
from edos.engines.providers.gemini_provider import GeminiProvider

_REAL_PROVIDERS = {"gemini": GeminiProvider, "anthropic": AnthropicProvider}


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
    effective = _effective_vendor() if settings.llm_provider not in ("", "stub") else None
    return {
        "selected": settings.llm_provider,
        "effective": effective or "stub",
        "auto_selected": bool(effective and effective != settings.llm_provider),
        "live": primary is not None,
        "primary": type(primary).__name__ if primary else "StubProvider",
        "fallback": type(fallback).__name__ if fallback else None,
        "gemini_key_present": bool(settings.gemini_api_key),
        "anthropic_key_present": bool(settings.anthropic_api_key),
    }


__all__ = ["AnthropicProvider", "GeminiProvider", "build_live_provider", "build_providers", "provider_status"]

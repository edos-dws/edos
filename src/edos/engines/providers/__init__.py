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


def build_providers():
    """Resolve (primary, fallback) providers for the Model Router from config.

    Primary = the `EDOS_PROVIDER` vendor (default 'gemini'). If the *other* vendor also has a key, it becomes
    the cross-vendor fallback (Ch 9) — e.g. Gemini decides, Anthropic covers a repair miss. Returns
    `(None, None)` when the primary can't run live, so the router stays on the offline stub.
    """
    primary = build_live_provider(settings.llm_provider)
    if primary is None:
        return None, None
    other = "anthropic" if settings.llm_provider == "gemini" else "gemini"
    fallback = build_live_provider(other)
    return primary, fallback


def provider_status() -> dict:
    """Diagnostics for the health endpoint: what the router will actually use, without exposing secrets."""
    primary, fallback = build_providers()
    return {
        "selected": settings.llm_provider,
        "live": primary is not None,
        "primary": type(primary).__name__ if primary else "StubProvider",
        "fallback": type(fallback).__name__ if fallback else None,
        "gemini_key_present": bool(settings.gemini_api_key),
        "anthropic_key_present": bool(settings.anthropic_api_key),
    }


__all__ = ["AnthropicProvider", "GeminiProvider", "build_live_provider", "build_providers", "provider_status"]

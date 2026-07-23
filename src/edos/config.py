"""Runtime configuration from environment (roadmap Ch 17). No secrets hard-coded.

LLM provider selection lives here so the platform is model- and vendor-agnostic: the engines never name a
vendor, they route by capability through the Model Router, and the router picks a provider from these
settings. Go-live is a config change (drop a key in `.env`), not a code change — everything below reads from
the environment, and when no key is present the router falls back to the deterministic StubProvider so tests
and CI run fully offline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Load `.env` (gitignored) so go-live is "drop the key in .env" with no code change. `override=False` means a
# real shell/CI/Docker environment variable always wins over the file — and the test suite forces
# EDOS_PROVIDER=stub, so a local `.env` with real keys can never pull tests onto the network. No-op if
# python-dotenv isn't installed.
try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:  # pragma: no cover - optional dependency
    pass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://edos:edos@localhost:5432/edos"
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # --- LLM provider selection (Ch 4: "route by capability, not vendor") ---
    # Which vendor the router uses when a key is available. "gemini" (default for now) or "anthropic".
    # "stub" forces the offline fixture provider regardless of keys (used by tests/CI).
    llm_provider: str = os.environ.get("EDOS_PROVIDER", "gemini").strip().lower()

    # Secrets — read from the environment only; never commit a real value. `.env` is gitignored.
    gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")

    # Model IDs per capability tier, env-overridable. Defaults are current-generation IDs; confirm the
    # exact Gemini strings against your account (Google occasionally renames tiers).
    gemini_frontier_model: str = os.environ.get("GEMINI_FRONTIER_MODEL", "gemini-2.5-pro")
    gemini_standard_model: str = os.environ.get("GEMINI_STANDARD_MODEL", "gemini-2.5-flash")
    gemini_lightweight_model: str = os.environ.get("GEMINI_LIGHTWEIGHT_MODEL", "gemini-2.5-flash")

    # Anthropic model IDs are the exact current-generation strings (do not append date suffixes).
    anthropic_frontier_model: str = os.environ.get("ANTHROPIC_FRONTIER_MODEL", "claude-opus-4-8")
    anthropic_standard_model: str = os.environ.get("ANTHROPIC_STANDARD_MODEL", "claude-sonnet-5")
    anthropic_lightweight_model: str = os.environ.get("ANTHROPIC_LIGHTWEIGHT_MODEL", "claude-haiku-4-5")

    # Hard ceiling on output tokens per LLM call (per-attempt safety cap; the prompt's own token_budget is a
    # separate, softer target). Kept modest so a decision fits comfortably.
    llm_max_output_tokens: int = int(os.environ.get("EDOS_LLM_MAX_OUTPUT_TOKENS", "8000"))

    def key_for(self, provider: str) -> str:
        """Return the configured API key for a provider name ('gemini' | 'anthropic'), or '' if unset."""
        return {"gemini": self.gemini_api_key, "anthropic": self.anthropic_api_key}.get(provider, "")


settings = Settings()

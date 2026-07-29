"""Runtime configuration from environment (roadmap Ch 17). No secrets hard-coded.

LLM provider selection lives here so the platform is model- and vendor-agnostic: the engines never name a
vendor, they route by capability through the Model Router, and the router picks a provider from these
settings. Go-live is a config change (drop a key in `.env`), not a code change — everything below reads from
the environment, and when no key is present the router falls back to the deterministic StubProvider so tests
and CI run fully offline.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# --- Gemini model fallback chains (per capability tier) ---------------------------------------------------
# Each Gemini model has its OWN rate/quota limit. When the primary model returns HTTP 429 RESOURCE_EXHAUSTED,
# a single-model provider fails outright and the engines drop to static heuristics (bad UX). Instead, each
# tier holds an ORDERED chain of text models: on a retriable error (429 / quota / rate limit, or a 404
# "model not found" when an id is wrong) the provider tries the NEXT model in the chain, only raising once the
# whole chain is exhausted. Tiers are separated so cheap tasks (question generation, intent) burn the Lite
# models and preserve the good model's limited quota for heavy tasks (decisions, challenge).
#
# These are the BEST-order defaults (text models only). The names are display-name→API-id GUESSES; correct
# any that don't map to a real API id via the *_CHAIN env overrides below (comma-separated), e.g.
#   GEMINI_FRONTIER_CHAIN="gemini-3.6-flash,gemini-2.5-flash"
# NOTE: the Gemini Embedding models (Embedding 1/2) are deliberately NOT in these chains — they belong to a
# real embedder (a separate change that needs a pgvector dimension migration), not the text generation path.
# TTS and Robotics models are likewise excluded.
_FRONTIER_CHAIN_DEFAULT: tuple[str, ...] = (
    "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash", "gemini-2.5-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite",
    "gemma-4-31b", "gemma-4-26b",
)
_STANDARD_CHAIN_DEFAULT: tuple[str, ...] = (
    "gemini-3-flash", "gemini-2.5-flash",
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite",
    "gemma-4-31b", "gemma-4-26b",
)
_LIGHTWEIGHT_CHAIN_DEFAULT: tuple[str, ...] = (
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite",
    "gemma-4-31b", "gemma-4-26b",
)


def _chain_from_env(env_var: str, default: tuple[str, ...]) -> tuple[str, ...]:
    """Parse a comma-separated `*_CHAIN` env var into an ordered model list. When the var is unset or empty,
    fall back to the given default LIST (not a single model) so a missing override still gets full fallback."""
    raw = os.environ.get(env_var, "")
    items = tuple(x.strip() for x in raw.split(",") if x.strip())
    return items or default

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

    # --- Hybrid (cost-split) routing -----------------------------------------------------------------------
    # Keep the PREMIUM provider (Claude/frontier) ONLY for the heavy decision-generation calls — the deep-dive
    # `decide`/`revise` and the `/v1/analyze` decision (frontier-tier `decision`/`deepdive`) — and route
    # EVERYTHING ELSE (intent, questions, follow-ups, verification, grounding, challenge, findings, knowledge
    # extraction, semantic edges) to the cheaper BASE provider (Gemini). This slashes cost for testing while
    # keeping the actual decision on the best model. OFF by default (all calls go to `EDOS_PROVIDER`); set
    # EDOS_HYBRID_ROUTING=1 to enable. Needs both a premium and a base key; a vendor with no key degrades to
    # the other live vendor, else the stub. `EDOS_PROVIDER=stub` still forces everything offline (tests/CI).
    hybrid_routing: bool = os.environ.get("EDOS_HYBRID_ROUTING", "0").strip().lower() in ("1", "true", "yes")
    premium_provider: str = os.environ.get("EDOS_PREMIUM_PROVIDER", "anthropic").strip().lower()
    base_provider: str = os.environ.get("EDOS_BASE_PROVIDER", "gemini").strip().lower()

    # Model IDs per capability tier, env-overridable. Defaults are the current Flash family — verified working
    # on a Google AI Studio FREE-tier key (Pro models return free-tier quota `limit: 0`). `gemini-3.6-flash`
    # is the exact "Gemini Flash 3.6" the EDOS benchmark validated. On a PAID key, point the frontier tier at
    # a Pro model for maximum reasoning: GEMINI_FRONTIER_MODEL=gemini-pro-latest (or gemini-3.1-pro-preview).
    gemini_frontier_model: str = os.environ.get("GEMINI_FRONTIER_MODEL", "gemini-3.6-flash")
    gemini_standard_model: str = os.environ.get("GEMINI_STANDARD_MODEL", "gemini-3.6-flash")
    gemini_lightweight_model: str = os.environ.get("GEMINI_LIGHTWEIGHT_MODEL", "gemini-3.5-flash-lite")

    # Per-tier ordered fallback CHAINS (see the block above the class). The GeminiProvider walks a tier's
    # chain, trying the next model on a retriable error (429 / quota / rate / 404 not-found). Override any
    # chain end-to-end with a comma-separated env var; unset → the best-order default list above.
    gemini_frontier_chain: tuple[str, ...] = field(
        default_factory=lambda: _chain_from_env("GEMINI_FRONTIER_CHAIN", _FRONTIER_CHAIN_DEFAULT))
    gemini_standard_chain: tuple[str, ...] = field(
        default_factory=lambda: _chain_from_env("GEMINI_STANDARD_CHAIN", _STANDARD_CHAIN_DEFAULT))
    gemini_lightweight_chain: tuple[str, ...] = field(
        default_factory=lambda: _chain_from_env("GEMINI_LIGHTWEIGHT_CHAIN", _LIGHTWEIGHT_CHAIN_DEFAULT))

    # Anthropic model IDs are the exact current-generation strings (do not append date suffixes).
    anthropic_frontier_model: str = os.environ.get("ANTHROPIC_FRONTIER_MODEL", "claude-opus-4-8")
    anthropic_standard_model: str = os.environ.get("ANTHROPIC_STANDARD_MODEL", "claude-sonnet-5")
    anthropic_lightweight_model: str = os.environ.get("ANTHROPIC_LIGHTWEIGHT_MODEL", "claude-haiku-4-5")

    # Hard ceiling on output tokens per LLM call (per-attempt safety cap; the prompt's own token_budget is a
    # separate, softer target). Kept modest so a decision fits comfortably.
    llm_max_output_tokens: int = int(os.environ.get("EDOS_LLM_MAX_OUTPUT_TOKENS", "8000"))

    # ---- Embeddings (semantic retrieval). Provider-agnostic: swap the model/provider with env, no code change.
    # `EDOS_EMBEDDER`: "gemini" | "stub" | "auto" (default). "auto" = gemini when a Gemini key is present, else
    # the deterministic offline stub (so tests/CI stay offline). `EDOS_EMBED_MODEL` picks the Gemini embedding
    # model (both gemini-embedding-001 and gemini-embedding-2 are 3072-dim, truncated to EDOS_EMBED_DIM via
    # Matryoshka + re-normalised). EDOS_EMBED_DIM must match the pgvector column dimension (768).
    embedder: str = os.environ.get("EDOS_EMBEDDER", "auto").strip().lower()
    embed_model: str = os.environ.get("EDOS_EMBED_MODEL", "gemini-embedding-001")

    # Reranker (retrieval precision). "auto" (default) = gemini when a key exists, else the no-op reranker.
    # `EDOS_RERANK_MODEL` picks a cheap model (Lite) so reranking stays cheap vs the decision call.
    reranker: str = os.environ.get("EDOS_RERANKER", "auto").strip().lower()
    rerank_model: str = os.environ.get("EDOS_RERANK_MODEL", "gemini-3.5-flash-lite")

    # Query expansion (retrieval recall). "auto" (default) = HyDE when a key exists, else no-op. Reuses the
    # cheap Lite model (rerank_model). Applied on the decision retrieval path only, so cost stays bounded.
    query_expansion: str = os.environ.get("EDOS_QUERY_EXPANSION", "auto").strip().lower()

    # Auto-run the independent LLM verification critic on the /v1/analyze path (A2). OFF by default: it can
    # lower confidence and add freeze_blockers on the main decision path, and (with a key) roughly doubles the
    # frontier calls per analyze — opt-in until trusted. Offline it degrades to the deterministic floor (free).
    # `/v1/verify` always runs the critic regardless of this flag (it is an explicit verification request).
    verify_on_analyze: bool = os.environ.get("EDOS_VERIFY_ON_ANALYZE", "0").strip().lower() in ("1", "true", "yes")

    # Layer-2 semantic grounding (A1): when set, /v1/analyze passes the retrieved context TEXT to the
    # faithfulness gate so an LLM NLI judge checks each claim is actually *supported* (entails), not merely
    # cited. OFF by default (needs a key; offline it degrades to Layer-1 traceability anyway) — opt-in until
    # measured against a labeled grounding set. One batched, standard-tier call per decision.
    grounding_nli: bool = os.environ.get("EDOS_GROUNDING_NLI", "0").strip().lower() in ("1", "true", "yes")

    # Semantic graph edges (A5): when set, ingesting an item runs an LLM pass that classifies its relationship
    # to its nearest neighbours and adds low-stakes edges (high-stakes conflict/supersede are surfaced for
    # confirmation, never auto-applied). OFF by default — adds an LLM call per ingest, changes the graph, and
    # is only meaningful with real embeddings (A4) + measured against the edge-quality eval. Offline no-op.
    semantic_edges: bool = os.environ.get("EDOS_SEMANTIC_EDGES", "0").strip().lower() in ("1", "true", "yes")

    def key_for(self, provider: str) -> str:
        """Return the configured API key for a provider name ('gemini' | 'anthropic'), or '' if unset."""
        return {"gemini": self.gemini_api_key, "anthropic": self.anthropic_api_key}.get(provider, "")


settings = Settings()

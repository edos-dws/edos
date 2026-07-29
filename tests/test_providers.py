"""Provider layer — vendor-agnostic wiring (Gemini + Anthropic), all offline.

No network, no vendor SDK required: providers import their SDK lazily and construction never dials out. The
LLM call path is exercised with injected fake clients so the parse/return logic and tier-gated params are
covered without a key.
"""
import pytest

from edos.engines.model_router import Capability, ModelRouter, StubProvider, Tier
from edos.engines.providers import (
    AnthropicProvider,
    GeminiProvider,
    build_live_provider,
    build_providers,
    provider_status,
)
from edos.engines.providers._common import extract_json, resolve_model, result_dict
from edos.models.decision import decision_contract


# --- JSON extraction -------------------------------------------------------
def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_prose_wrapped():
    assert extract_json('Here is the decision:\n{"a": 1, "b": [2,3]}\nDone.') == {"a": 1, "b": [2, 3]}


def test_extract_json_malformed_returns_sentinel():
    out = extract_json("not json at all")
    assert out == {"_malformed": "not json at all"}


def test_result_dict_no_schema_wraps_text():
    assert result_dict(Capability.intent, None, "hello") == {"capability": "intent", "text": "hello"}


def test_result_dict_with_schema_parses():
    assert result_dict(Capability.decision, {"type": "object"}, '{"x": 1}') == {"x": 1}


# --- tier → model resolution ----------------------------------------------
def test_resolve_model_picks_tier():
    models = {Tier.frontier: "F", Tier.standard: "S", Tier.lightweight: "L"}
    assert resolve_model(Capability.decision, models) == "F"  # decision is frontier
    assert resolve_model(Capability.clarification, models) == "S"  # standard
    assert resolve_model(Capability.intent, models) == "L"  # lightweight


# --- factory selection -----------------------------------------------------
def test_factory_stub_and_empty_return_none():
    assert build_live_provider("stub") is None
    assert build_live_provider("") is None


def test_factory_unknown_provider_raises():
    with pytest.raises(ValueError):
        build_live_provider("openai")


def test_factory_builds_right_class_when_key_present():
    assert isinstance(build_live_provider("gemini", key="k"), GeminiProvider)
    assert isinstance(build_live_provider("anthropic", key="k"), AnthropicProvider)


def test_factory_returns_none_without_key():
    assert build_live_provider("gemini", key="") is None
    assert build_live_provider("anthropic", key="") is None


def test_construction_is_lazy_no_sdk_needed():
    # Constructing a provider must not import the vendor SDK or touch the network.
    p = GeminiProvider(api_key="k")
    assert p._client is None
    assert p._chains[Tier.frontier]  # per-tier fallback chain resolved from config


def test_build_providers_offline_under_stub_env():
    # conftest forces EDOS_PROVIDER=stub → no live provider, router stays on the stub.
    assert build_providers() == (None, None)
    status = provider_status()
    assert status["live"] is False and status["primary"] == "StubProvider"


# --- provider auto-selection safety-net (the silent-stub footgun) ----------
import dataclasses

from edos.config import settings as _settings


def _with_settings(monkeypatch, **over):
    """Point the providers module at a Settings clone with overridden provider/keys (frozen → replace)."""
    monkeypatch.setattr("edos.engines.providers.settings", dataclasses.replace(_settings, **over))


def test_configured_vendor_with_its_key_is_used(monkeypatch):
    _with_settings(monkeypatch, llm_provider="anthropic", anthropic_api_key="ak", gemini_api_key="")
    primary, fallback = build_providers()
    assert isinstance(primary, AnthropicProvider)
    assert fallback is None  # other vendor unkeyed → no cross-vendor fallback


def test_auto_selects_keyed_vendor_when_configured_vendor_has_no_key(monkeypatch):
    # THE footgun: EDOS_PROVIDER left at 'gemini' but only an Anthropic key was dropped in .env.
    # Old behaviour: gemini has no key → (None, None) → every call silently ran on the stub.
    _with_settings(monkeypatch, llm_provider="gemini", gemini_api_key="", anthropic_api_key="ak")
    primary, fallback = build_providers()
    assert isinstance(primary, AnthropicProvider)  # auto-substituted the vendor that actually has a key
    assert fallback is None
    status = provider_status()
    assert status["live"] is True
    assert status["selected"] == "gemini" and status["effective"] == "anthropic"
    assert status["auto_selected"] is True  # visible, not silent


def test_explicit_stub_stays_stub_even_with_real_keys(monkeypatch):
    # EDOS_PROVIDER=stub is explicit and must win — keeps tests/CI offline even if real keys are present.
    _with_settings(monkeypatch, llm_provider="stub", gemini_api_key="gk", anthropic_api_key="ak")
    assert build_providers() == (None, None)
    assert provider_status()["auto_selected"] is False


def test_both_keys_give_cross_vendor_fallback(monkeypatch):
    _with_settings(monkeypatch, llm_provider="anthropic", anthropic_api_key="ak", gemini_api_key="gk")
    primary, fallback = build_providers()
    assert isinstance(primary, AnthropicProvider)
    assert isinstance(fallback, GeminiProvider)  # the other keyed vendor covers a repair miss (Ch 9)


def test_no_keys_falls_back_to_stub(monkeypatch):
    _with_settings(monkeypatch, llm_provider="anthropic", anthropic_api_key="", gemini_api_key="")
    assert build_providers() == (None, None)


def test_unknown_provider_still_raises_loud(monkeypatch):
    # a typo must fail loudly, NOT silently auto-pick a keyed vendor.
    _with_settings(monkeypatch, llm_provider="openai", anthropic_api_key="ak", gemini_api_key="gk")
    with pytest.raises(ValueError):
        build_providers()


# --- hybrid (cost-split) routing: premium for decision generation, base for the rest --------------------
from edos.engines.providers import HybridProvider


class _Rec:
    """Records which lane a call was routed to."""
    def __init__(self, name):
        self.name = name

    def execute(self, capability, context, schema=None, prompt=None, tier=None):
        return {"by": self.name}


def test_hybrid_routes_decision_generation_to_premium_everything_else_to_base():
    h = HybridProvider(_Rec("premium"), _Rec("base"))
    # decide / revise → Capability.deepdive at frontier tier → PREMIUM (Claude)
    assert h.execute(Capability.deepdive, {}, tier=Tier.frontier)["by"] == "premium"
    # /v1/analyze decision (no tier override → frontier by default) → PREMIUM
    assert h.execute(Capability.decision, {})["by"] == "premium"
    # everything else → BASE (Gemini): verification is frontier but NOT a premium capability
    assert h.execute(Capability.verification, {})["by"] == "base"
    # deep-dive questions / follow-ups → Capability.deepdive at lightweight tier → BASE
    assert h.execute(Capability.deepdive, {}, tier=Tier.lightweight)["by"] == "base"
    for cap in (Capability.intent, Capability.grounding, Capability.challenge,
                Capability.findings, Capability.relationship, Capability.knowledge_extraction):
        assert h.execute(cap, {})["by"] == "base"


def test_hybrid_falls_to_other_live_vendor_before_stub():
    # base vendor unkeyed → a base-lane call uses the premium vendor (a real model), NOT a silent stub
    h = HybridProvider(_Rec("premium"), None)
    assert h.execute(Capability.intent, {})["by"] == "premium"


def test_hybrid_uses_stub_only_when_neither_vendor_live():
    h = HybridProvider(None, None)
    out = h.execute(Capability.intent, {}, schema=None, prompt="p")
    assert out == {"capability": "intent", "stub": True}  # deterministic stub


def test_build_providers_hybrid_returns_hybrid_and_status(monkeypatch):
    _with_settings(monkeypatch, llm_provider="anthropic", hybrid_routing=True,
                   anthropic_api_key="ak", gemini_api_key="gk")
    primary, fallback = build_providers()
    assert isinstance(primary, HybridProvider)
    assert fallback is primary  # the hybrid already picks a live vendor per call
    status = provider_status()
    assert status["hybrid_routing"] is True
    assert status["premium"] == "anthropic" and status["base"] == "gemini"
    assert status["premium_live"] is True and status["base_live"] is True


def test_hybrid_stub_env_stays_offline(monkeypatch):
    # EDOS_PROVIDER=stub still wins over hybrid → fully offline (tests/CI), even with real keys present.
    _with_settings(monkeypatch, llm_provider="stub", hybrid_routing=True,
                   anthropic_api_key="ak", gemini_api_key="gk")
    assert build_providers() == (None, None)


# --- router auto-selection -------------------------------------------------
def test_router_defaults_to_stub_when_no_live_provider():
    assert isinstance(ModelRouter().provider, StubProvider)


def test_router_uses_configured_live_provider(monkeypatch):
    fake = GeminiProvider(api_key="k")
    monkeypatch.setattr("edos.engines.model_router._configured_providers", lambda: (fake, None))
    router = ModelRouter()
    assert router.provider is fake
    assert router.fallback is fake  # no fallback configured → falls back to primary


# --- LLM call path via injected fake clients (no SDK) ----------------------
class _FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeAnthropicClient:
    def __init__(self, text):
        self.captured = {}
        self._text = text
        self.messages = self

    def create(self, **kwargs):
        self.captured = kwargs
        return type("Resp", (), {"content": [_FakeBlock(self._text)]})()


def test_anthropic_execute_parses_and_gates_thinking_by_tier():
    p = AnthropicProvider(api_key="k")
    fake = _FakeAnthropicClient('{"summary": "ok"}')
    p._client = fake  # inject; no real SDK

    out = p.execute(Capability.decision, context={}, schema=decision_contract(), prompt="PROMPT")
    assert out == {"summary": "ok"}
    # frontier tier → adaptive thinking + effort passed; prompt forwarded verbatim
    assert fake.captured["thinking"] == {"type": "adaptive"}
    assert fake.captured["output_config"] == {"effort": "high"}
    assert fake.captured["messages"][0]["content"] == "PROMPT"

    # lightweight tier (Haiku) must NOT receive thinking/effort (it rejects them)
    p2 = AnthropicProvider(api_key="k")
    fake2 = _FakeAnthropicClient('{"capability": "intent"}')
    p2._client = fake2
    p2.execute(Capability.intent, context={}, schema=None, prompt="P")
    assert "thinking" not in fake2.captured and "output_config" not in fake2.captured


class _FakeGeminiModels:
    def __init__(self, text):
        self.captured = {}
        self._text = text

    def generate_content(self, **kwargs):
        self.captured = kwargs
        return type("Resp", (), {"text": self._text})()


class _FakeGeminiClient:
    def __init__(self, text):
        self.models = _FakeGeminiModels(text)


def test_gemini_execute_parses_output():
    p = GeminiProvider(api_key="k")
    p._client = _FakeGeminiClient('```json\n{"summary": "ok"}\n```')  # inject

    out = p.execute(Capability.decision, context={}, schema=decision_contract(), prompt="PROMPT")
    assert out == {"summary": "ok"}
    assert p._client.models.captured["model"]  # a frontier model id was chosen
    assert p._client.models.captured["contents"] == "PROMPT"

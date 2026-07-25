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

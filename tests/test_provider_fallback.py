"""Gemini model fallback chain + per-capability tier override — all offline, no live LLM, no SDK.

Each Gemini model has its own quota. When the primary returns 429 RESOURCE_EXHAUSTED a single-model provider
fails outright and the engines drop to static heuristics. `GeminiProvider` instead walks an ordered per-tier
chain, trying the next model on a retriable error. These tests drive that with a fake client (an object with
`.models.generate_content(...)` we control) — the network is never touched.
"""
import pytest

from edos.engines.model_router import Capability, Tier
from edos.engines.providers import GeminiProvider


# --- a controllable fake Gemini client (no SDK, no network) ---------------------------------------
class _FakeGeminiError(Exception):
    """Stands in for an SDK error; `code` mimics the numeric status some SDK exceptions expose."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class _RecordingModels:
    """`generate_content` looks up per-model behaviour: raise a configured exception, or return text."""

    def __init__(self, behaviors: dict) -> None:
        self._behaviors = behaviors  # model_id -> Exception (to raise) | str (text to return)
        self.calls: list[str] = []   # ordered list of model ids actually attempted

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        action = self._behaviors.get(model, '{"ok": true}')
        if isinstance(action, Exception):
            raise action
        return type("Resp", (), {"text": action})()


class _FakeGeminiClient:
    def __init__(self, models: _RecordingModels) -> None:
        self.models = models


def _provider_with(chains: dict[Tier, list[str]], behaviors: dict) -> GeminiProvider:
    p = GeminiProvider(api_key="k")
    p._chains = chains
    p._client = _FakeGeminiClient(_RecordingModels(behaviors))  # inject; no real SDK
    return p


# --- (a) 429 on the first model(s), then success further down the chain ---------------------------
def test_falls_forward_past_429_to_a_working_model():
    chains = {Tier.standard: ["m1", "m2", "m3"], Tier.frontier: ["x"], Tier.lightweight: ["y"]}
    behaviors = {
        "m1": _FakeGeminiError("429 RESOURCE_EXHAUSTED: quota exceeded", code=429),
        "m2": _FakeGeminiError("RESOURCE_EXHAUSTED", code=429),
        "m3": '{"summary": "served by m3"}',
    }
    p = _provider_with(chains, behaviors)

    out = p.execute(Capability.clarification, context={}, schema={"type": "object"}, prompt="P")

    assert out == {"summary": "served by m3"}       # the later model's result, no exception raised
    assert p.last_model == "m3"                       # records which model actually served the call
    assert p._client.models.calls == ["m1", "m2", "m3"]  # walked the chain in order


# --- (b) a non-retriable error (auth) raises immediately, no chain-walking ------------------------
def test_non_retriable_auth_error_raises_immediately():
    chains = {Tier.standard: ["m1", "m2"], Tier.frontier: ["x"], Tier.lightweight: ["y"]}
    behaviors = {"m1": _FakeGeminiError("401 UNAUTHENTICATED: invalid API key", code=401)}
    p = _provider_with(chains, behaviors)

    with pytest.raises(_FakeGeminiError):
        p.execute(Capability.clarification, context={}, schema={"type": "object"}, prompt="P")
    assert p._client.models.calls == ["m1"]  # stopped at the auth failure; did NOT try m2


# --- (c) whole chain exhausted → the last error propagates ----------------------------------------
def test_all_models_exhausted_raises_last_error():
    chains = {Tier.standard: ["m1", "m2"], Tier.frontier: ["x"], Tier.lightweight: ["y"]}
    last = _FakeGeminiError("429 quota", code=429)
    behaviors = {"m1": _FakeGeminiError("rate limit", code=429), "m2": last}
    p = _provider_with(chains, behaviors)

    with pytest.raises(_FakeGeminiError) as excinfo:
        p.execute(Capability.clarification, context={}, schema={"type": "object"}, prompt="P")
    assert excinfo.value is last
    assert p._client.models.calls == ["m1", "m2"]


# --- 404 "model not found" (a wrong id) is treated as retriable -----------------------------------
def test_404_not_found_is_retriable():
    chains = {Tier.standard: ["bad-id", "good"], Tier.frontier: ["x"], Tier.lightweight: ["y"]}
    behaviors = {
        "bad-id": _FakeGeminiError("404 NOT_FOUND: models/bad-id is not found", code=404),
        "good": '{"ok": 1}',
    }
    p = _provider_with(chains, behaviors)
    out = p.execute(Capability.clarification, context={}, schema={"type": "object"}, prompt="P")
    assert out == {"ok": 1}
    assert p.last_model == "good"


# --- (d) tier override picks the lightweight chain, not the capability's default tier -------------
def test_tier_override_selects_the_lightweight_chain():
    # `clarification` is a STANDARD capability; passing tier=lightweight must use the lightweight chain.
    chains = {Tier.standard: ["S"], Tier.frontier: ["F"], Tier.lightweight: ["L"]}
    p = _provider_with(chains, behaviors={"L": '{"from": "lite"}', "S": '{"from": "std"}'})

    out = p.execute(Capability.clarification, context={}, schema={"type": "object"},
                    prompt="P", tier=Tier.lightweight)
    assert out == {"from": "lite"}
    assert p._client.models.calls == ["L"]          # lightweight chain, NOT the standard one
    assert p.last_model == "L"


def test_no_tier_override_uses_capability_default_tier():
    chains = {Tier.standard: ["S"], Tier.frontier: ["F"], Tier.lightweight: ["L"]}
    p = _provider_with(chains, behaviors={"S": '{"from": "std"}'})
    p.execute(Capability.clarification, context={}, schema={"type": "object"}, prompt="P")  # standard cap
    assert p._client.models.calls == ["S"]

    p2 = _provider_with(chains, behaviors={"F": '{"from": "frontier"}'})
    p2.execute(Capability.decision, context={}, schema={"type": "object"}, prompt="P")  # frontier cap
    assert p2._client.models.calls == ["F"]


# --- _is_retriable decision table -----------------------------------------------------------------
@pytest.mark.parametrize("exc", [
    _FakeGeminiError("429 RESOURCE_EXHAUSTED"),
    _FakeGeminiError("quota exceeded for the day"),
    _FakeGeminiError("rate limit reached"),
    _FakeGeminiError("404 model not found"),
    _FakeGeminiError("boom", code=429),
    _FakeGeminiError("boom", code=404),
])
def test_is_retriable_true_cases(exc):
    assert GeminiProvider._is_retriable(exc) is True


@pytest.mark.parametrize("exc", [
    _FakeGeminiError("401 UNAUTHENTICATED"),
    _FakeGeminiError("permission denied"),
    _FakeGeminiError("invalid argument: contents too long"),
    _FakeGeminiError("boom", code=401),
    ValueError("some other bug"),
])
def test_is_retriable_false_cases(exc):
    assert GeminiProvider._is_retriable(exc) is False


# --- chains come from config (env-overridable, best-order defaults) --------------------------------
def test_default_chains_loaded_from_config():
    p = GeminiProvider(api_key="k")
    # frontier is the longest chain and leads with the benchmark-validated model; lightweight is Lite-only.
    assert p._chains[Tier.frontier][0] == "gemini-3.6-flash"
    assert len(p._chains[Tier.frontier]) >= len(p._chains[Tier.standard]) >= len(p._chains[Tier.lightweight])
    assert all("lite" in m or "gemma" in m for m in p._chains[Tier.lightweight])

"""The router renders the authored prompt and hands it to the provider (prompt implementation)."""
from edos.engines.model_router import Capability, ModelRouter
from edos.models.decision import Decision, decision_contract
from edos.prompts.render import prompt_ref_for, render


def test_decision_capability_maps_to_decision_prompt():
    assert prompt_ref_for(Capability.decision) == "decision_prompt:v1"
    assert prompt_ref_for(Capability.verification) == "verification_prompt:v1"


def test_render_composes_template_context_and_schema():
    text = render(Capability.decision, {"project_id": "p1", "items": []}, decision_contract())
    assert "CONTEXT PACKAGE" in text
    assert "project_id" in text
    assert "OUTPUT SCHEMA" in text
    assert "edos.decision.v1" in text          # the template + schema both mention it
    assert "Never invent project data" in text  # ERC core made it into the prompt


class _SpyProvider:
    """Captures the rendered prompt the router passes in, then returns a valid decision."""

    def __init__(self):
        self.seen_prompt = None

    def execute(self, capability, context, schema, prompt=None):
        self.seen_prompt = prompt
        return Decision(
            summary="s", recommendation="r", confidence=0.5, status="recommended",
            evidence=[{"claim": "c", "source": "stub"}],
        ).to_contract_dict()


def test_router_passes_a_rendered_prompt_to_the_provider():
    spy = _SpyProvider()
    ModelRouter(provider=spy).execute(Capability.decision, {"project_id": "p1"}, decision_contract())
    assert spy.seen_prompt is not None
    assert "CONTEXT PACKAGE" in spy.seen_prompt
    assert "project_id" in spy.seen_prompt

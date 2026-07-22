"""Quality gates on the production prompt templates (Step 1 deliverable).

These are lightweight, deterministic checks that the prompts encode the non-negotiable behaviours the
validated benchmark runs demonstrated — so a future edit can't silently drop them.
"""
from edos.prompts.registry import all_specs, load_template


def test_every_prompt_template_loads_and_is_nonempty():
    for spec in all_specs():
        text = load_template(spec.ref)
        assert text.strip(), f"{spec.ref} template is empty"


def test_reasoning_templates_substitute_erc_core():
    for ref in ("decision_prompt:v1", "verification_prompt:v1"):
        text = load_template(ref)
        assert "{{ERC_CORE}}" not in text, f"{ref} left the ERC marker unsubstituted"
        assert "Never invent project data" in text, f"{ref} missing the no-invention rule"


def test_decision_prompt_encodes_core_behaviours():
    text = load_template("decision_prompt:v1").lower()
    # generic, embedded-wide reasoning — not tied to any single domain
    assert "embedded" in text
    # must produce the locked JSON contract
    assert "edos.decision.v1" in text
    # safety / freeze discipline
    assert "freeze_blockers" in text
    assert 'status' in text and 'recommended' in text  # never verified/frozen
    # never guess missing inputs
    assert "next_actions" in text
    assert "do not" in text or "never" in text


def test_verification_prompt_is_lower_only_and_critique():
    text = load_template("verification_prompt:v1").lower()
    assert "do not" in text and "regenerate" in text  # critique, not regenerate
    assert "lower" in text  # confidence can only be lowered


def test_no_domain_lock_in_core():
    # the core principles must be generic — not hard-coded to the benchmark domains
    core = load_template("decision_prompt:v1").lower()
    for domain_word in ("lmfp", "lorawan", "ptz", "zigbee", "nrf52840"):
        assert domain_word not in core, f"prompt is over-fit to a specific domain: {domain_word}"

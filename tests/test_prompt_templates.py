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


def test_erc_core_encodes_four_archetypes_and_reasoning_method():
    # ERC core is the shared reasoning brain — it must carry the principal-embedded machinery,
    # not just a stance. Checked via a template that substitutes it.
    text = load_template("decision_prompt:v1").lower()
    # four senior archetypes present
    for archetype in ("senior embedded engineer", "systems engineer", "principal engineer",
                      "solution architect"):
        assert archetype in text, f"ERC core missing archetype: {archetype}"
    # the reasoning METHOD (not just stance)
    assert "constraints before options" in text
    assert "runner-up" in text          # show the line + the option it beat
    assert "second-order ripple" in text
    # the break-the-loop mandate — EDOS's embedded-specific edge
    assert "premature part-lock" in text
    assert "silent contradiction" in text
    # preserved guarantees still intact after the upgrade
    assert "never invent project data" in text


def test_deepdive_decide_encodes_crystallized_card_content():
    # Wave 3 · Step 7 — the card is the closing argument, not a static dump.
    text = load_template("deepdive_prompt:v1").lower()
    assert "runner_up" in text and "tipped_by" in text           # show the #2 option + what tipped it
    assert "blind_spots" in text and "distinct from" in text      # blind spots ≠ risks
    assert "tripwires" in text                                    # review_conditions are pre-committed flips
    assert "provenance" in text and "computed:" in text          # tag computed vs datasheet vs inferred
    assert "show the line" in text                                # recommendation reads as an argument
    assert "computations" in text and "re-evaluate" in text       # #8: model emits checkable arithmetic


def test_no_domain_lock_in_core():
    # the core principles must be generic — not hard-coded to the benchmark domains
    core = load_template("decision_prompt:v1").lower()
    for domain_word in ("lmfp", "lorawan", "ptz", "zigbee", "nrf52840"):
        assert domain_word not in core, f"prompt is over-fit to a specific domain: {domain_word}"

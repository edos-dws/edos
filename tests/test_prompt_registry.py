"""Ticket 3.2 — Prompt registry: versioned lookup + valid output-schema references."""
import pytest

from edos.prompts.registry import (
    PromptSpec,
    all_specs,
    get,
    known_schema_ids,
    register,
)


def test_lookup_by_ref():
    spec = get("decision_prompt:v1")
    assert spec.output_schema == "edos.decision.v1"
    assert spec.ref == "decision_prompt:v1"
    assert spec.token_budget > 0
    assert spec.template.endswith(".md")


def test_every_registered_prompt_names_a_known_schema():
    valid = known_schema_ids()
    for spec in all_specs():
        assert spec.output_schema in valid, f"{spec.ref} names unknown schema {spec.output_schema}"


def test_registering_unknown_schema_is_rejected():
    with pytest.raises(ValueError):
        register(PromptSpec("bad_prompt", "v1", "x", ("m",), "edos.not_a_schema.v9", 100,
                            "decision_prompt.v1.md"))


def test_known_schema_ids_include_locked_contracts():
    ids = known_schema_ids()
    assert "edos.decision.v1" in ids
    assert "edos.context_package.v1" in ids
    assert "none" in ids

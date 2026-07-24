"""Ticket 1.1 — the Decision model must agree with the locked decision contract."""
import jsonschema
import pytest
from pydantic import ValidationError

from edos.models.decision import Decision, DecisionStatus, validate_against_contract

VALID = {
    "summary": "Use STM32WL, not nRF52840",
    "recommendation": "Switch to an SoC with an integrated sub-GHz LoRa radio.",
    "confidence": 0.88,
    "status": "recommended",
    "evidence": [{"claim": "nRF52840 has no LoRa radio", "source": "proj:radio-note", "kind": "fact"}],
}


def test_valid_decision_passes_model_and_contract():
    d = Decision(**VALID)
    data = d.to_contract_dict()
    validate_against_contract(data)  # must not raise
    assert data["schema_version"] == "edos.decision.v1"
    assert data["status"] == "recommended"


def test_status_is_constrained_enum():
    assert {s.value for s in DecisionStatus} == {"proposed", "recommended", "verified", "frozen"}


def test_missing_evidence_fails_model():
    payload = {k: v for k, v in VALID.items() if k != "evidence"}
    with pytest.raises(ValidationError):
        Decision(**payload)


def test_confidence_out_of_range_fails():
    with pytest.raises(ValidationError):
        Decision(**{**VALID, "confidence": 1.5})


def test_unknown_status_fails():
    with pytest.raises(ValidationError):
        Decision(**{**VALID, "status": "frozenish"})


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        Decision(**{**VALID, "surprise": 123})


def test_contract_rejects_malformed_dict():
    with pytest.raises(jsonschema.ValidationError):
        validate_against_contract({"summary": "x"})  # missing required fields


def test_freeze_blockers_default_empty():
    # Default state carries no freeze blockers; the freeze gate (CP-9) will populate them.
    d = Decision(**VALID)
    assert d.freeze_blockers == []

"""Ticket 1.2 — the ContextPackage model must agree with its locked contract."""
import jsonschema
import pytest
from pydantic import ValidationError

from edos.models.context import ContextPackage, validate_against_contract

VALID = {
    "project_id": "agrisense-n1",
    "intent": "architecture_review",
    "entities": ["LoRaWAN", "solar", "nRF52840"],
    "items": [
        {"type": "decision", "ref_id": "D-1", "content": "MCU=nRF52840", "score": 0.9},
        {"type": "requirement", "ref_id": "R-3", "content": "report every 10s", "score": 0.6},
    ],
}


def test_valid_package_passes_model_and_contract():
    cp = ContextPackage(**VALID)
    validate_against_contract(cp.to_contract_dict())  # must not raise


def test_items_are_returned_highest_score_first():
    cp = ContextPackage(**VALID)
    scores = [it.score for it in cp.ranked_items()]
    assert scores == sorted(scores, reverse=True)
    assert cp.ranked_items()[0].ref_id == "D-1"


def test_missing_items_fails():
    payload = {k: v for k, v in VALID.items() if k != "items"}
    with pytest.raises(ValidationError):
        ContextPackage(**payload)


def test_bad_item_type_fails():
    with pytest.raises(ValidationError):
        ContextPackage(**{**VALID, "items": [{"type": "nonsense", "content": "x", "score": 0.5}]})


def test_score_out_of_range_fails():
    with pytest.raises(ValidationError):
        ContextPackage(**{**VALID, "items": [{"type": "project", "content": "x", "score": 2.0}]})


def test_contract_rejects_malformed_dict():
    with pytest.raises(jsonschema.ValidationError):
        validate_against_contract({"project_id": "x"})  # missing required

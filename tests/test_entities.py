"""Ticket 1.3 — core domain entities and the 11-type graph Edge."""
import pytest

from edos.models.entities import (
    Alert,
    Assumption,
    Component,
    Document,
    Edge,
    KnowledgeItem,
    Project,
    RelationType,
    Requirement,
    Risk,
)


def test_all_eleven_relation_types_present():
    assert {r.value for r in RelationType} == {
        "depends_on", "created_by", "influences", "supersedes", "conflicts_with",
        "mitigates", "references", "derived_from", "validates", "invalidates", "related_to",
    }
    assert len(RelationType) == 11


def test_construct_each_entity():
    Project(id="p1", name="AgriSense", domain="agri-iot")
    Requirement(id="R1", project_id="p1", statement="report telemetry")
    Assumption(id="A1", project_id="p1", statement="solar suffices", confidence=0.9)
    Component(id="C1", project_id="p1", name="MCU", part_number="STM32WL")
    Risk(id="K1", project_id="p1", description="energy deficit", severity="high", likelihood="high")
    Document(id="Doc1", project_id="p1", title="datasheet")
    KnowledgeItem(id="Kn1", project_id="p1", content="LoRaWAN is duty-cycle limited")
    Alert(id="Al1", project_id="p1", message="check duty cycle")


def test_edge_enforces_relation_type():
    e = Edge(source_id="D-1", target_id="R-3", relation_type=RelationType.conflicts_with, confidence=0.8)
    assert e.relation_type == RelationType.conflicts_with
    with pytest.raises(Exception):
        Edge(source_id="a", target_id="b", relation_type="teleports_to")


def test_confidence_bounds_enforced():
    with pytest.raises(Exception):
        Assumption(id="A2", project_id="p1", statement="x", confidence=1.4)


def test_extra_fields_forbidden():
    with pytest.raises(Exception):
        Project(id="p1", name="X", surprise=1)

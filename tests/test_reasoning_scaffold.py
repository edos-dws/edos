"""Wave 2 · Step 5 — the reasoning scaffold: project-conditioned prompt assembly + Deep Dive wiring."""
from edos.engines import reasoning_scaffold as rs


def test_scaffold_is_project_conditioned(monkeypatch):
    # THE payoff of the whole wave: identical decision, two projects → two different reasoning scaffolds.
    monkeypatch.setattr(rs, "_coverage_fraction", lambda s, p: 1.0)

    monkeypatch.setattr(rs, "_project_corpus",
                        lambda s, p: "embedded Linux Yocto Cortex-A MIPI CSI camera video Ethernet mains EU")
    linux = rs.build_scaffold(None, "p1", "select the main component for the node")

    monkeypatch.setattr(rs, "_project_corpus",
                        lambda s, p: "Cortex-M FreeRTOS Li-ion battery BLE IP68 sealed wearable")
    batt = rs.build_scaffold(None, "p1", "select the main component for the node")

    assert linux["text"] != batt["text"]
    # spine fingerprints differ
    assert any("compute_tier: linux" in ln for ln in linux["spine_lines"])
    assert any("power_source: battery" in ln for ln in batt["spine_lines"])
    # the battery project pulls the POWER lens into deep reasoning (full frame text present)
    batt_deep_ids = {d["id"] for d in batt["deep"]}
    assert "power" in batt_deep_ids
    assert "worst-case" in batt["text"].lower()          # a phrase from power.md's frame


def test_scaffold_always_has_direction_and_lens_sections(monkeypatch):
    monkeypatch.setattr(rs, "_coverage_fraction", lambda s, p: 1.0)
    monkeypatch.setattr(rs, "_project_corpus", lambda s, p: "Cortex-M mains BLE")
    out = rs.build_scaffold(None, "p1", "pick a radio")
    assert "PROJECT DIRECTION" in out["text"]
    assert "REASON WITH THESE LENSES" in out["text"]
    # blind-spot floor: the scan section exists and lists lenses not chosen for depth
    assert out["scan"], "scan (blind-spot floor) lenses should always be present"


def test_empty_project_renders_all_unknown_honestly(monkeypatch):
    monkeypatch.setattr(rs, "_project_corpus", lambda s, p: "")
    monkeypatch.setattr(rs, "_coverage_fraction", lambda s, p: 0.0)
    out = rs.build_scaffold(None, "p1", "some decision")
    assert out["text"]                                    # renders, never errors
    # honest thin render: nothing derived => every axis reported as unknown (asked later, never guessed)
    assert "unknown (not yet established)" in out["text"]
    assert not out["deep"]                                # thin context => no lens goes deep


def test_deepdive_scaffold_helper_never_raises():
    # best-effort: even a dummy session must not break decision reasoning — returns the dict, never raises.
    from edos.engines.deepdive import _reasoning_scaffold
    result = _reasoning_scaffold(object(), "p1", "topic")
    assert isinstance(result, dict)
    assert set(result) == {"text", "spine", "lenses"}     # text for prompt; spine+lenses for the UI/audit


def test_plan_frame_shape_is_reasoning_first():
    # the FRAME is what EDOS reflects back before deciding — understanding + spine + lenses + framing questions.
    from edos.engines.deepdive import plan_frame
    frame = plan_frame(object(), "p1", "select the radio")   # dummy session => minimal but well-formed
    assert set(frame) >= {"topic", "understanding", "spine", "framing_questions", "lenses"}
    assert frame["topic"] == "select the radio"
    assert isinstance(frame["lenses"], list)


def test_deepdive_prompt_instructs_use_of_scaffold():
    from edos.prompts.registry import load_template
    text = load_template("deepdive_prompt:v1")
    assert "reasoning_scaffold" in text
    assert "spine" in text.lower() and "lens" in text.lower()

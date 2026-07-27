"""Feature 2 — learned lens weights: outcomes self-tune which lenses lead for a project direction."""
import json
from types import SimpleNamespace

from edos.engines import feedback, lens_weighting, spine


def _decision_with_frame(spine_lines, deep_lens_ids):
    frame = {"spine": spine_lines,
             "lenses": [{"lens_id": lid, "deep": True} for lid in deep_lens_ids]}
    return SimpleNamespace(decision_detail=json.dumps({"reasoning_frame": frame}))


def test_accepted_boosts_deep_lenses_for_that_direction(session):
    row = _decision_with_frame(["power_source: battery", "connectivity: wireless"], ["power"])
    n = feedback.apply_lens_feedback(session, decision_row=row, outcome="accepted")
    assert n == 2  # 2 spine keys × 1 deep lens

    sp = spine.classify("battery powered BLE device")  # power_source:battery + connectivity:wireless
    learned = feedback.lens_learned_weights(session, sp)
    assert learned.get("power", 0.0) > 0.0     # the load-bearing lens was rewarded
    assert "cost" not in learned                # a lens that wasn't deep is not boosted

    # weigh() reflects it: power ranks a little higher WITH the learned nudge than without
    w_no = {w.lens_id: w.weight for w in lens_weighting.weigh(sp, "sensor choice")}
    w_yes = {w.lens_id: w.weight for w in lens_weighting.weigh(sp, "sensor choice", learned=learned)}
    assert w_yes["power"] > w_no["power"]


def test_reversed_penalises_the_lens(session):
    row = _decision_with_frame(["power_source: battery"], ["power"])
    feedback.apply_lens_feedback(session, decision_row=row, outcome="reversed")
    sp = spine.classify("battery device")
    learned = feedback.lens_learned_weights(session, sp)
    assert learned.get("power", 0.0) < 0.0


def test_learned_nudge_is_bounded(session):
    # even a large accumulated score contributes at most ±DELTA_LEARNED to the weight
    sp = spine.classify("battery device")
    huge = {"power": 999.0}
    w = {x.lens_id: x.weight for x in lens_weighting.weigh(sp, "x", learned=huge)}
    base = {x.lens_id: x.weight for x in lens_weighting.weigh(sp, "x")}
    assert 0 < (w["power"] - base["power"]) <= lens_weighting.DELTA_LEARNED + 1e-9


def test_unknown_axis_and_non_deep_lens_are_ignored(session):
    # 'unknown' spine line and non-deep lenses must not produce feedback rows
    frame = {"spine": ["unknown (not yet established): realtime, markets"],
             "lenses": [{"lens_id": "power", "deep": False}]}
    row = SimpleNamespace(decision_detail=json.dumps({"reasoning_frame": frame}))
    assert feedback.apply_lens_feedback(session, decision_row=row, outcome="accepted") == 0

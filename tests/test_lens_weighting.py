"""Wave 2 · Step 4 — the weighting engine: project-conditioned, topic-refined, floor-protected."""
from edos.engines import spine
from edos.engines.lens_weighting import (
    BLIND_SPOT_FLOOR,
    CONSTRAINT_MIN,
    weigh,
)


def _w(weights, lens_id):
    return next(x for x in weights if x.lens_id == lens_id)


def test_same_topic_different_projects_weight_differently():
    # THE core promise: identical decision, two projects, different reasoning emphasis.
    topic = "select the main component for the sensor node"
    linux_cam = spine.classify("embedded Linux Yocto i.MX Cortex-A, MIPI CSI camera video over Ethernet, mains")
    batt_ble = spine.classify("Cortex-M MCU FreeRTOS, Li-ion battery, BLE, IP68 sealed wearable")

    w_linux = weigh(linux_cam, topic)
    w_batt = weigh(batt_ble, topic)

    # Linux/streaming project weights PCB & peripherals higher; battery project weights POWER higher.
    assert _w(w_linux, "pcb").weight > _w(w_batt, "pcb").weight
    assert _w(w_batt, "power").weight > _w(w_linux, "power").weight
    assert _w(w_batt, "connectivity_rf").weight > _w(w_linux, "connectivity_rf").weight


def test_clear_spine_keeps_differentiation_at_low_coverage():
    """Regression: flattening must key on SPINE confidence, not coverage%. A directionally-clear project at
    LOW coverage% (few tagged items / unanswered questions) must keep its project-conditioned emphasis — the
    earlier coverage-only flattening washed it out, collapsing every lens to the mean."""
    clear = spine.classify(
        "Wrist band, CR2032 coin cell, 6-month life, BLE 5.0, IP68 sealed, mass production, nRF52 Cortex-M")
    assert len(clear.values) >= 6  # a confident spine
    ws = weigh(clear, "power regulation approach", coverage=0.08)  # thin coverage, clear direction
    top = sorted(ws, key=lambda w: w.weight, reverse=True)
    spread = top[0].weight - top[4].weight
    assert spread > 0.3, f"clear spine collapsed at low coverage (spread {spread:.3f})"
    assert _w(ws, "power").weight == top[0].weight  # power still dominates a coin-cell power decision


def test_vague_project_flattens_and_asks():
    """The counterpart: a project with almost no established direction SHOULD flatten toward the mean so EDOS
    doesn't over-commit on weak signal (the framing intake asks instead)."""
    vague = spine.classify("We need to pick a component for the project.")
    assert len(vague.values) <= 2  # thin spine
    ws = weigh(vague, "which part", coverage=0.08)
    top = sorted(ws, key=lambda w: w.weight, reverse=True)
    # the non-constraint lenses cluster near the mean (no strong differentiation)
    non_constraint = [w for w in top if w.lens_id not in ("bom_supply", "cost")]
    assert non_constraint[0].weight - non_constraint[4].weight < 0.15


def test_topic_lifts_an_off_spine_lens():
    # a Linux project asking specifically about the enclosure must lift the enclosure lens for THIS decision.
    linux = spine.classify("embedded Linux on Cortex-A, Ethernet, mains powered")
    generic = weigh(linux, "choose the main processor")
    enclosure_q = weigh(linux, "how do we seal the enclosure against water ingress (IP68 gasket)")
    assert _w(enclosure_q, "mechanical_enclosure").weight > _w(generic, "mechanical_enclosure").weight


def test_blind_spot_floor_never_drops_a_lens():
    r = spine.classify("Cortex-M MCU, mains powered, indoor")   # thermal/rf largely off-spine
    weights = weigh(r, "pick a debug connector")
    assert all(x.weight >= BLIND_SPOT_FLOOR for x in weights)
    # even an irrelevant lens is still present (scan floor), never dropped from the list
    assert any(x.lens_id == "connectivity_rf" for x in weights)


def test_constraints_always_surfaced():
    r = spine.classify("prototype, one-off, mains")
    weights = weigh(r, "pick an op-amp")
    assert _w(weights, "bom_supply").weight >= CONSTRAINT_MIN
    assert _w(weights, "cost").weight >= CONSTRAINT_MIN


def test_depth_is_bounded_and_frame_backed():
    r = spine.classify("Li-ion battery BLE wearable, Cortex-M, EU market")
    weights = weigh(r, "select the power management and radio")
    deep = [x for x in weights if x.deep]
    assert len(deep) <= 5
    # anything marked deep must actually have a frame to go deep with
    from edos.engines import lenses
    for x in deep:
        assert lenses.get_lens(x.lens_id).frame_file, f"{x.lens_id} marked deep but has no frame"


def test_engineer_override_wins():
    r = spine.classify("Cortex-M MCU, mains")
    base = weigh(r, "pick a crystal")
    boosted = weigh(r, "pick a crystal", overrides={"certification": 0.99})
    assert _w(boosted, "certification").weight == 0.99
    assert _w(boosted, "certification").weight > _w(base, "certification").weight


def test_low_coverage_flattens_weights():
    r = spine.classify("Li-ion battery BLE wearable Cortex-M")
    full = weigh(r, "select the radio", coverage=1.0)
    thin = weigh(r, "select the radio", coverage=0.2)
    spread_full = max(x.weight for x in full) - min(x.weight for x in full)
    spread_thin = max(x.weight for x in thin) - min(x.weight for x in thin)
    assert spread_thin < spread_full   # thinner context => less committed, flatter weights

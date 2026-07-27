"""Wave 2 · Step 2 — the reasoning lens library: structure, blind-spot floor, and versioned frames."""
from edos.engines import lenses


def test_registry_nonempty_and_covers_physical_and_software_halves():
    ids = set(lenses.lens_ids())
    # both halves of embedded must be represented (the physical-realization half was the gap we closed)
    assert {"compute_tier", "realtime_concurrency", "memory", "firmware_arch"} <= ids   # software
    assert {"pcb", "mechanical_enclosure", "thermal"} <= ids                            # physical
    assert {"certification", "reliability_safety", "security", "bom_supply"} <= ids     # trust/supply


def test_every_lens_has_a_blind_spot_floor():
    # the floor: no lens may exist without a scan_line — weighting sets depth, never gates a concern off.
    for lens in lenses.all_lenses():
        assert lens.scan_line.strip(), f"{lens.id} has no scan_line (blind-spot floor)"
        assert lens.title.strip()
        assert 0.0 <= lens.base <= 1.0


def test_affinity_keys_are_axis_value_form_and_positive():
    for lens in lenses.all_lenses():
        for key, weight in lens.affinities.items():
            assert ":" in key, f"{lens.id}: affinity key {key!r} is not 'axis:value'"
            assert weight > 0, f"{lens.id}: affinity {key} should be a positive contribution"


def test_top_common_lenses_have_loadable_frames():
    # the five most-common decision types ship a full reasoning frame (depth); others are scan-only for now.
    for lens_id in ("compute_tier", "power", "pcb", "connectivity_rf", "certification"):
        lens = lenses.get_lens(lens_id)
        assert lens is not None
        frame = lens.load_frame()
        assert frame and len(frame) > 200, f"{lens_id} frame missing or too thin"
        assert "###" in frame  # the frame is a real markdown reasoning block


def test_every_lens_has_a_scan_line_blind_spot_floor():
    # The blind-spot floor: EVERY lens always carries a scan_line, so a low-weight lens is never dropped —
    # it degrades to its scan line, it never disappears. (Scan-vs-deep is decided by WEIGHT in the weighting
    # engine, not by whether a frame exists — all 18 lenses now carry a full frame.)
    for lens in lenses.all_lenses():
        assert lens.scan_line and lens.scan_line.strip(), f"{lens.id} has no scan_line (blind-spot floor)"


def test_lens_without_frame_file_degrades_to_none_frame():
    # `load_frame()` must return None (not error) when a lens has no frame_file — the mechanism that lets a
    # frameless lens fall back to its scan_line. Verified on a synthetic lens so it holds even now that all
    # shipped lenses carry a frame.
    bare = lenses.Lens(id="x", title="X", affinities={}, structural_triggers=(), scan_line="scan")
    assert bare.frame_file is None
    assert bare.load_frame() is None


def test_bom_and_cost_are_present_as_constraints():
    # BOM availability & cost exist in the library (the weighting engine applies them as constraints).
    assert lenses.get_lens("bom_supply") is not None
    assert lenses.get_lens("cost") is not None

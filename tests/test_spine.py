"""Wave 2 · Step 3 — the spine classifier: derive project direction, ask (never guess) the unknowns."""
from edos.engines import spine


def test_linux_camera_project_fingerprint():
    corpus = """
    The gateway runs embedded Linux (Yocto) on an i.MX Cortex-A SoC. It streams video from a MIPI CSI
    camera over Ethernet. Mains-powered, indoor industrial deployment, targeting the EU market.
    """
    r = spine.classify(corpus)
    assert r.values["compute_tier"] == "linux"
    assert r.values["data_char"] == "streaming"
    assert r.values["connectivity"] == "wired"       # ethernet
    assert r.values["power_source"] == "mains"


def test_battery_ble_medical_project_fingerprint_differs():
    corpus = """
    A wearable patient monitor on a Cortex-M MCU with FreeRTOS. Battery-powered (Li-ion), communicates over
    BLE. Medical device under IEC 62304. Sealed, waterproof (IP68) enclosure.
    """
    r = spine.classify(corpus)
    assert r.values["compute_tier"] in ("mcu", "rtos")   # both signalled; either is defensible
    assert r.values["power_source"] == "battery"
    assert r.values["connectivity"] == "wireless"
    assert r.values["criticality"] == "medical"
    assert r.values["form_factor"] == "sealed"
    assert r.values["environment"] == "harsh"


def test_unknown_axes_are_reported_not_guessed():
    r = spine.classify("A device that does something.")   # no real signal
    # nothing derivable => everything unknown, nothing invented
    assert not r.values
    assert set(r.unknown) == {a.key for a in spine.SPINE_AXES}


def test_framing_questions_target_top_unknowns_only():
    r = spine.classify("Battery-powered BLE sensor.")     # power + connectivity known; rest unknown
    qs = spine.framing_questions(r, max_q=3)
    assert 1 <= len(qs) <= 3
    asked = {q["axis"] for q in qs}
    # never re-ask what we already derived
    assert "power_source" not in asked
    assert "connectivity" not in asked
    # highest-importance unknowns come first (compute_tier is importance 1.0)
    assert qs[0]["axis"] == "compute_tier"


def test_signals_are_an_audit_trail():
    r = spine.classify("Li-ion battery, BLE radio.")
    # the derivation basis is exposed (non-fabricated): the hits that drove each value
    assert r.signals.get("power_source:battery", 0) >= 1
    assert r.signals.get("connectivity:wireless", 0) >= 1


def test_no_substring_false_positives():
    """Triggers are whole terms, not substrings: 'secure'/'performance'/'interface'/'input' must NOT be read
    as ecu(automotive)/rf(wireless)/npu(edge-ai) — the bare-`in` matcher did exactly that and corrupted the
    spine, poisoning the framing questions and every downstream lens weight."""
    r = spine.classify(
        "The device has secure boot and a high-performance user interface for input handling.")
    assert "criticality" not in r.values      # 'ecu' ⊄ 'secure'
    assert "connectivity" not in r.values      # 'rf' ⊄ 'surface'/'interface'/'performance'
    assert "data_char" not in r.values         # 'npu' ⊄ 'input'
    # and 'pid' must not be read out of 'rapid'
    assert spine.classify("a rapid prototype").values.get("data_char") != "control"


def test_real_terms_still_classify_after_boundary_fix():
    """The boundary fix must not lose genuine signals."""
    assert spine.classify("Automotive ECU, ISO 26262, CAN bus").values.get("criticality") == "automotive"
    assert spine.classify("BLE and Wi-Fi with an antenna, RF front-end").values.get("connectivity") == "wireless"
    assert spine.classify("TinyML neural inference on an NPU").values.get("data_char") == "edge_ai"

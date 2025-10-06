import time
from picker.hw import SimulatedMCP3008, HW, Calibration, KnobMapper


def test_raw_to_pos_basic():
    calib = Calibration(adc_min=0, adc_max=1023, inverted=False, positions=12)
    mapper = KnobMapper(calib, stable_required=1)

    # raw 0 should map to 0
    pos, changed = mapper.map(0)
    assert pos == 0

    # raw close to top should map to last position
    pos, changed = mapper.map(1023)
    assert pos == 11

    # mid-range
    mid_raw = (1023 // 2)
    pos, changed = mapper.map(mid_raw)
    assert 0 <= pos < 12


def test_hysteresis_and_stability():
    calib = Calibration(adc_min=0, adc_max=1023, inverted=False, positions=12)
    mapper = KnobMapper(calib, stable_required=3)

    # noisy around a boundary: alternate values that would flip mapping if unstable
    vals = [100, 105, 102, 107, 101, 103]
    last_pos = None
    changed_count = 0
    for v in vals:
        pos, changed = mapper.map(v)
        if changed:
            changed_count += 1
            last_pos = pos
    # With stable_required=3 we expect few or no changes for noisy sequence
    assert changed_count <= 2


def test_hw_read_positions_and_buttons():
    sim = SimulatedMCP3008()
    hw = HW(adc_reader=sim)

    # set CH0 to a value and ensure mapping
    sim.set_channel(0, 512)
    positions = hw.read_positions()
    assert 0 in positions
    pos, changed = positions[0]
    assert 0 <= pos < 12

    # test buttons (simulate pressed by setting ADC high)
    sim.set_channel(3, 900)
    btns = hw.read_buttons()
    assert btns.get('GO') is True

    sim.set_channel(7, 0)
    btns = hw.read_buttons()
    assert btns.get('RESET') is False


if __name__ == "__main__":
    # Run tests directly for environments without pytest available.
    test_raw_to_pos_basic()
    test_hysteresis_and_stability()
    test_hw_read_positions_and_buttons()
    print("OK")

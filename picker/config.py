"""Default configuration loader for picker.

This module exposes a small `load_texts` helper that reads a JSON configuration of knob
labels and returns a validated dict ready for the UI code. It also provides default
calibration placeholders which `picker/hw.py` will use.
"""

from pathlib import Path
import json
from typing import Dict, Any

DEFAULT_SAMPLE = Path(__file__).with_name("sample_texts.json")

DEFAULT_CALIBRATION = {
    "adc_min": 0,
    "adc_max": 1023,
    "inverted": False,
    "positions": 12,
    "hysteresis": 0.015,  # 1.5%
}

DEFAULT_DISPLAY = {
    "reserve_image_width": 512,
    "reserve_image_height": 512,
    "poll_hz": 80,
    "max_partial_updates_per_sec": 30,
}


def load_texts(path: str = None) -> Dict[str, Any]:
    """Load and validate texts JSON. If `path` is None, use the bundled sample file.

    Returns the parsed JSON as a dict and performs basic validation (each knob has 12 values).
    """
    p = Path(path) if path else DEFAULT_SAMPLE
    if not p.exists():
        raise FileNotFoundError(f"Text config not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Basic validation
    knobs = ["CH0", "CH1", "CH2", "CH4", "CH5", "CH6"]
    for k in knobs:
        if k not in data:
            raise ValueError(f"Missing knob entry in text config: {k}")
        if "title" not in data[k] or "values" not in data[k]:
            raise ValueError(f"Knob {k} must contain 'title' and 'values' fields")
        if not isinstance(data[k]["values"], list) or len(data[k]["values"]) != 12:
            raise ValueError(f"Knob {k} 'values' must be an array of length 12")

    return data


if __name__ == "__main__":
    # Quick smoke test when run directly
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = load_texts(path)
    print("Loaded knob config keys:", list(cfg.keys()))

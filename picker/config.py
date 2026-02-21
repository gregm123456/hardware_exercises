"""Default configuration loader for picker.

This module exposes a small `load_texts` helper that reads a JSON configuration of knob
labels and returns a validated dict ready for the UI code. It also provides default
calibration placeholders which `picker/hw.py` will use.

Rotary encoder support
----------------------
``load_menus`` converts a texts JSON file (CH0..CH6 format *or* the new
``menus`` list format) into an ordered list of ``(title, values)`` tuples
suitable for :class:`picker.rotary_core.RotaryPickerCore`.

New flexible JSON format (``menus`` key)::

    {
        "menus": [
            {"title": "Colour", "values": ["Red", "Blue", "Green"]},
            {"title": "Size",   "values": ["S", "M", "L"]}
        ]
    }

The legacy CH0/CH1/... format is also accepted; channels are sorted
numerically and converted to the same tuple list.
"""

from pathlib import Path
import json
from typing import Any, Dict, List, Tuple

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

# ---------------------------------------------------------------------------
# Default GPIO BCM pin assignments for the rotary encoder
# ---------------------------------------------------------------------------
DEFAULT_ROTARY_PIN_CLK: int = 22  # CLK / A output
DEFAULT_ROTARY_PIN_DT: int = 23   # DT  / B output
DEFAULT_ROTARY_PIN_SW: int = 27   # SW  (pushbutton, active-LOW)

# Default button debounce time in milliseconds
DEFAULT_ROTARY_DEBOUNCE_MS: int = 50



def load_menus(path: str = None) -> List[Tuple[str, List[str]]]:
    """Load a texts JSON and return an ordered list of ``(title, values)`` tuples.

    Accepts **both** formats:

    * **Legacy CH-key format** – keys ``CH0``, ``CH1``, ... each with
      ``"title"`` and ``"values"`` sub-keys.  Channels are sorted numerically
      and converted to the tuple list.
    * **New ``menus`` list format** – a top-level ``"menus"`` key containing
      a JSON array of objects, each with ``"title"`` and ``"values"`` keys.
      Values may be any non-empty list of strings (no length restriction).

    If ``path`` is ``None`` the bundled :data:`DEFAULT_SAMPLE` file is used.

    Returns
    -------
    list of (title, values) tuples
        Ordered list of menus ready for
        :class:`picker.rotary_core.RotaryPickerCore`.

    Raises
    ------
    FileNotFoundError
        If the JSON file cannot be found.
    ValueError
        If the file is missing required fields or is otherwise malformed.
    """
    p = Path(path) if path else DEFAULT_SAMPLE
    if not p.exists():
        raise FileNotFoundError(f"Text config not found: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # ------------------------------------------------------------------
    # New "menus" list format
    # ------------------------------------------------------------------
    if "menus" in data:
        entries = data["menus"]
        if not isinstance(entries, list) or len(entries) == 0:
            raise ValueError("'menus' must be a non-empty JSON array")
        result: List[Tuple[str, List[str]]] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"menus[{i}] must be a JSON object")
            if "title" not in entry or "values" not in entry:
                raise ValueError(
                    f"menus[{i}] must have 'title' and 'values' keys"
                )
            title = str(entry["title"])
            values = entry["values"]
            if not isinstance(values, list) or len(values) == 0:
                raise ValueError(
                    f"menus[{i}] 'values' must be a non-empty array"
                )
            # Filter out blank strings so the UI doesn't show empty rows
            values = [str(v) for v in values if str(v).strip()]
            if not values:
                raise ValueError(
                    f"menus[{i}] 'values' contains no non-blank entries"
                )
            result.append((title, values))
        return result

    # ------------------------------------------------------------------
    # Legacy CH-key format (CH0, CH1, CH2, CH4, CH5, CH6)
    # ------------------------------------------------------------------
    ch_keys = sorted(
        (k for k in data if isinstance(k, str) and k.startswith("CH")),
        key=lambda k: int(k[2:]),
    )
    if not ch_keys:
        raise ValueError(
            "JSON config has neither a 'menus' key nor any 'CH*' keys"
        )

    result = []
    for k in ch_keys:
        entry = data[k]
        if not isinstance(entry, dict):
            raise ValueError(f"Entry for {k!r} must be a JSON object")
        if "title" not in entry or "values" not in entry:
            raise ValueError(
                f"Entry for {k!r} must have 'title' and 'values' keys"
            )
        title = str(entry["title"])
        values = [str(v) for v in entry["values"] if str(v).strip()]
        if not values:
            raise ValueError(
                f"Entry for {k!r} 'values' contains no non-blank entries"
            )
        result.append((title, values))

    return result


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

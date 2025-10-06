Picker — README
================

This `picker/` package provides a standalone selection UI driven by six 12-position knobs
and two buttons. The plan and implementation goals are in `picker_plan.md` at the repo root.

Quick start (simulate)
----------------------

1. Create a virtualenv and install Python requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r picker/requirements.txt
```

2. Run the smoke loader which validates the sample JSON config:

```bash
python -m picker.config
```

3. Next steps: implement hw/ui/core modules or run `picker/run_picker.py --simulate` when ready.

File layout
-----------
- `sample_texts.json` — canonical sample of knob titles and 12-values arrays
- `config.py` — loader and defaults
- `hw.py`, `ui.py`, `core.py`, `drivers/` — to be implemented

Design notes
------------
- The UI prefers full-screen overlays for readability. A reserved image area exists for future use.
- The sample JSON allows empty strings in value slots.

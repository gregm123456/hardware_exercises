(The file `/Users/gregm/ACE/ePaper/hardware_exercises/README.md` exists, but is empty)
# hardware_exercises — E-Paper utilities and examples

This repository contains small utilities, examples, and helper scripts for
working with IT8951-based e-paper displays (Waveshare panels) and a few
related hardware utilities (MCP3008 ADC helpers, reset utilities, etc.).

Important: the `IT8951/` directory is supplied as a repository submodule or
local driver copy and provides the low-level driver and display classes.
Treat the `IT8951` package as an external driver: the rest of this repo
contains higher-level helpers and example scripts that use it.

## Quick overview

- Purpose: provide utilities to prepare images and update IT8951-driven
	displays (including a virtual display for development), plus a few
	convenience scripts for resetting and probing connected hardware.
- Key helper package: `update_waveshare/` — image preparation and a small
	CLI wrapper (`simple_update.py`).
- Driver: `IT8951/` — low-level controller code (submodule / external
	dependency). See `python_epaper_usage_guide.md` for a walkthrough of the
	driver API.

## Contents (important files)

- `IT8951/` — local copy or submodule of the IT8951 Python driver. Not a
	unique part of this project; the helpers here expect an IT8951-compatible
	package to be importable.
- `update_waveshare/` — helpers that prepare images and send them to the
	display. Contains `core.py`, `_device.py`, and `simple_update.py`.
- `python_epaper_usage_guide.md` — usage guide summarizing the IT8951 API,
	modes, and examples (useful reference when working with the driver).
- `update_waveshare/requirements.txt` — runtime dependency list for the
	helpers (Pillow).
- Top-level scripts and helpers:
	- `simple_update.py` (convenience wrapper; duplicate exists under
		`update_waveshare/` as a module entrypoint)
	- `blank_screen.py`, `restore_display.py`, `aggressive_reset.py`,
		`force_reinit.py`, `reset_controller.py`, `smart_reset.py` — utilities to
		clear displays, manage resets, or re-initialise hardware.
	- `probe_device.py` — helper to probe connected SPI/GPIO devices.
	- `mcp3008_*.py` and `mcp3008_calibrator.py` — simple helpers for using an
		MCP3008 ADC (calibration and voltmeter examples).

## Requirements

- Python 3.7+ (the code uses modern Python but is intentionally lightweight)
- Pillow (for image handling) — required by `update_waveshare` and the
	example scripts.
- The `IT8951` package (provided in `IT8951/` or installable separately via
	pip). If `IT8951` is not available on your `PYTHONPATH`, the helpers try
	to add the repository-local `IT8951` path automatically.

Install the helpers' runtime requirements:

```bash
pip install -r update_waveshare/requirements.txt
```

Install the IT8951 driver from this repository (optional extras for RPi GPIO):

```bash
pip install ./
# Or, with Raspberry Pi GPIO support:
pip install '.[rpi]'
```

## Quick usage

Display an image on a virtual display (fast verification on a desktop):

```bash
python update_waveshare/simple_update.py /path/to/image.png --virtual
```

Blank the (real) display:

```bash
python update_waveshare/simple_update.py --blank
```

Programmatically from Python (example):

```python
from update_waveshare.core import display_image

# display_image returns a list of updated regions (bboxes) or an empty list
regions = display_image('photo.png', virtual=True)
print('Updated regions:', regions)
```

Notes about partial updates and VCOM
- The helpers will attempt partial updates when a previous image is supplied
	and the computed difference bbox is small enough; otherwise a full update
	is used. See `update_waveshare/README.md` and `python_epaper_usage_guide.md`
	for details on display modes (GC16, DU, etc.) and pixel packing.
- The `vcom` parameter controls panel VCOM voltage; try slightly different
	negative floats to tweak contrast.

## Hardware setup notes

- Enable SPI on single-board computers (Raspberry Pi `raspi-config` -> SPI).
- Ensure the running user is in `spi` and `gpio` groups if applicable:

```bash
sudo usermod -aG spi,gpio $USER
```

- If you see communication errors, reduce `spi_hz` used when creating the
	`AutoEPDDisplay` or `EPD` object (the usage guide uses 24 MHz as a
	reasonable default but not all platforms tolerate it).

## Troubleshooting

- ImportError for `IT8951`: either install the driver into your environment
	(pip install ./IT8951 or pip install it8951 if published) or make sure
	the local `IT8951/` directory is present and contains the package source.
- Strange artifacts: try different `vcom` values and/or run a full update.
- Partial updates not working: ensure `prev_image` is provided and that the
	computed bbox is non-empty; check alignment constraints (4/8-pixel
	boundaries).

## Developer notes

- `update_waveshare` intentionally focuses on image preparation and a small
	CLI; it expects a working `IT8951` driver to be available.
- `simple_update.py` offers a quick way to run things directly from the
	repository; prefer `python -m update_waveshare.simple_update` once the
	package is installed.

## Where to look next

- Read `python_epaper_usage_guide.md` for a compact summary of the `IT8951`
	driver's classes and methods (examples, partial update behaviour, VCOM).
- See `update_waveshare/README.md` for detailed options to `display_image()`
	and how CLI flags map to behavior.

If you'd like, I can also:
- Add a short example script that demonstrates a common workflow end-to-end.
- Create a small tests harness that runs in virtual mode and validates basic
	display-update paths.

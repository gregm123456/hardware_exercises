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

### Raspberry Pi 5 Support (Crucial)
The Raspberry Pi 5 uses a new hardware architecture (RP1 chipset) that requires specific handling for GPIO and SPI:

1. **Environment**: Create your virtual environment with `--system-site-packages` to access the Pi 5-specific `RPi.GPIO` and `libcamera` bindings provided by the OS:
   ```bash
   python -m venv .venv --system-site-packages
   ```
2. **Avoid Conflicts**: Do **not** install `RPi.GPIO` or `spidev` inside the venv via pip. These generic versions are incompatible with Pi 5. If they are already there, uninstall them:
   ```bash
   pip uninstall RPi.GPIO spidev
   ```
3. **IT8951 Build**: Rebuild the driver C-extensions whenever you change Python versions:
   ```bash
   cd IT8951 && pip install -e .
   ```

### General Setup
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

## Picker Subproject

The `picker/` folder contains a standalone UI application for selecting values
and triggering Stable Diffusion image generation, designed for headless
Raspberry Pi + e-paper display hardware but with full simulation support for
development on a workstation.

### Input modes

Two input strategies are supported and chosen at run time:

| Mode | Hardware | CLI flag |
|------|----------|----------|
| **ADC knobs** (original) | MCP3008 ADC · six 12-position rotary knobs · GO + RESET buttons | *(default)* |
| **Rotary encoder** (new) | One rotary encoder knob + pushbutton · five GPIO leads | `--rotary` |

The rotary encoder replaces all six ADC knobs and both buttons with a single
device. The user navigates a two-level hierarchical menu: rotate to scroll,
press to enter/select. The top level shows all menu names plus "Go" and
"Reset". Each submenu offers "↩ Return" to go back without changing the
current selection.

### Key Features
- **Rotary Encoder Input** (new): single GPIO encoder + pushbutton navigates
  a hierarchical menu. Menus and items are fully configurable; no fixed count.
- **Live Camera Streaming**: MJPEG stream of the camera view. Enable with
  `--stream` (default port 8088). Works with both input modes.
- **Stable Diffusion Integration**: `txt2img` and `img2img` generation modes.
  In `img2img`, the camera captures a still image on each GO press.
- **Calibration** (ADC mode): interactive calibration using
  `mcp3008_calibration.json`. The rotary encoder requires no calibration.
- **Flexible Config Format**: the new `menus`-list JSON format supports any
  number of menus with any number of items per menu. The legacy CH-key format
  (CH0…CH6 with exactly 12 items each) remains fully supported.
- **Rotation Support**: display content can be rotated (`CW`, `CCW`, `flip`).
- **Systemd Services**: `picker_startup.service` and
  `picker_camera_still_startup.service` for automatic startup.

### Running the Picker

Install requirements:
```bash
pip install -r picker/requirements.txt
```

Simulate — ADC knob mode:
```bash
PYTHONPATH=. python picker/run_picker.py --simulate --display-w 800 --display-h 600
```

Simulate — rotary encoder mode (no hardware required):
```bash
PYTHONPATH=. python picker/run_picker.py --rotary-simulate --display-w 800 --display-h 600
```

On hardware — ADC knob mode:
```bash
PYTHONPATH=. python picker/run_picker.py --display-w 1448 --display-h 1072 --display-spi-device 0
```

On hardware — rotary encoder mode (default BCM pins 17/18/27):
```bash
PYTHONPATH=. python picker/run_picker.py --rotary --display-w 1448 --display-h 1072
```

Enable live camera streaming (works with both modes):
```bash
PYTHONPATH=. python picker/run_picker.py --stream
PYTHONPATH=. python picker/run_picker.py --rotary --stream
```

### Troubleshooting
- Use `picker/diagnose_epaper.sh` to diagnose SPI and GPIO issues.
- Refer to `picker/README.md` for complete setup, wiring, and usage details.

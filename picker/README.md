Picker — Design, implementation, and usage
=========================================

This `picker/` package implements a small, standalone selection UI driven by six 12-position
knobs and two buttons. It's designed for headless hardware (Raspberry Pi + MCP3008 ADC +
e-paper display) but includes simulation paths so you can develop and test on a workstation.

This README explains the design, the implementation of each component, how to run the
project (simulate or on-device), calibration and testing instructions, and developer notes.

Quick summary
-------------
- Purpose: provide a compact UI for selecting values from six 12-item lists using physical
	rotary knobs (12 detents each) and two buttons (GO and RESET). The GO action uses a
	Stable Diffusion client to generate an image that can be shown on the display.
- Hardware: MCP3008 ADC (knobs), SPI-based e-paper display (IT8951 / Waveshare variants),
	running on a Linux platform such as Raspberry Pi.
- Simulation: all hardware paths are simulated so you can run and test on macOS/Linux
	without connected hardware.

Highlights
----------
- Stable knob mapping with per-knob calibration to avoid oscillation between adjacent
	detents.
- Display abstraction that supports several backends: update_waveshare, IT8951 Python
	package, a basic SPI implementation, and a simulated display used for development.
- A minimal core loop that polls HW, composes overlay images with Pillow, and pushes
	frames to the display adapter.

Project layout and responsibilities
----------------------------------
Top-level files (important ones):

- `run_picker.py` — CLI launcher. Handles arguments for simulation, display size,
	calibration file, and starting the interactive calibrator. Entry point for running the
	app.
- `config.py` — loads sample texts and provides defaults for calibration and display
	parameters. Contains `load_texts()` which validates the JSON structure (each knob has
	12 values).
- `mcp3008_calibration.json` — an example calibration file produced by the calibrator.

Core modules (package `picker/`):

- `hw.py` — hardware abstraction layer.
	- `SimulatedMCP3008`: simple in-memory ADC simulator for development and tests.
	- `Calibration` dataclass: holds per-knob calibration breakpoints and settings.
	- `KnobMapper`: maps raw ADC values to discrete positions (0..11) with hysteresis and
		a stability counter (debounce) to avoid flicker.
	- `HW`: higher-level helper that exposes `read_positions()` and `read_buttons()` using
		an ADC reader backend (simulator or real MCP3008).

- `ui.py` — UI composition utilities (Pillow).
	- `compose_overlay(title, values, selected_index, full_screen)`: creates the overlay
		image used by the picker UI; selected item is visually highlighted (inverted).
	- `compose_main_screen(...)` and `compose_message(...)`: full-screen main surface and
		small message screens. These are device-resolution aware and scale fonts for
		readability on e-paper.

- `core.py` — picker application core event loop and state machine.
	- Polls `HW` for knob changes and button presses.
	- Calls `compose_overlay` / `compose_main_screen` and writes frames to the display
		adapter (partial updates or full refreshes as appropriate).
	- Manages GO and RESET behavior; GO triggers the SD client logic to generate/receive an
		image (in the current implementation, this is driven by `sd_client.py`).

- `sd_client.py` — small client used by GO action to call an SD Web UI server and
	process returned images. Contains `_apply_gamma()` to adjust images for e-paper
	readability.

- `sd_config.py` — constants and defaults used by `sd_client` (e.g., server URL,
	EPAPER_GAMMA). This file is intentionally decoupled from runtime config so tests can
	mock it easily.

Driver folder (`picker/drivers/`):

- `display_fast.py` — a compact display adapter used by `core.py`. It wraps a
	`create_display(...)` factory and provides safe re-init, a lock around blits, and
	helper functions for partial/full updates and clearing the display. Also supports a
	filesystem-backed simulation mode that writes frames to `/tmp/picker_display` for
	debugging.
- `epaper_enhanced.py` — display factory that tries to pick the best available driver:
	1. `update_waveshare` package (preferred)
	2. `IT8951` package
	3. Basic SPI implementation (bundled)
	4. `SimulatedDisplay` fallback
	The module exports driver classes for each implementation and a `create_display()`
	convenience function.
- `epaper_standalone.py` — a self-contained IT8951 implementation (SPI + simple
	command set). Used when external dependencies aren't available.

Tests and development
---------------------
- `picker/tests/` contains unit and integration tests:
	- `test_hw_mapping.py` — checks `KnobMapper` mapping, hysteresis, and the
		`SimulatedMCP3008` behavior.
	- `test_ui.py` — sanity checks for `compose_overlay` (size and visual selection
		sampling).
	- `test_gamma.py`, `test_gamma_integration.py` — verify the gamma correction logic
		used for SD image processing.

Design and implementation details
---------------------------------

1) Knob mapping and stability

- Each knob is read via the MCP3008 ADC (0..1023 default). The `KnobMapper` converts
	raw ADC values to a normalized voltage and then maps that voltage to one of 12
	discrete positions.
- Per-knob calibration allows asymmetrical or non-linear breakpoints. The calibrator
	measures voltages for each detent and stores the per-channel voltage breakpoints in
	a JSON calibration file (see `mcp3008_calibration.json`).
- Hysteresis: mapping thresholds use midpoints between calibrated positions. A
	stability counter (`stable_required`) forces N consecutive maps to the same value
	before reporting a change. This prevents oscillation when hardware is noisy.

2) Display abstraction and updates

- The display factory tries to use the most capable driver available on the system
	(update_waveshare -> IT8951 -> Basic SPI -> Simulation). This keeps device-specific
	code out of the core logic.
- `display_fast.py` exposes a global display instance behind a lock to serialize updates
	and reinitializations. The adapter provides `blit()` (write single frames),
	`partial_update()` (rect), `full_update()` and `clear_display()` helpers.
- Simulation mode writes rendered frames to `/tmp/picker_display` and uses PIL to save
	PNG frames; it also allows `--force-simulation` at the CLI.

3) Image handling (Stable Diffusion + e-paper)

- When GO is pressed, `core.py` may call into `sd_client.generate_image()` which
	interacts with a Stable Diffusion Web UI server and writes a PNG image locally.
- SD images are adjusted with `_apply_gamma(img, gamma)` to brighten midtones and
	preserve dynamic range on monochrome/greyscale e-paper. The default gamma is in
	`sd_config.EPAPER_GAMMA` (1.8 by default).
- Generation parameters like `SD_STEPS`, `SD_CFG_SCALE`, and `SD_DENOISING_STRENGTH`
	(used for img2img mode) are configured in `sd_config.py`.

4) Performance considerations

- Poll rates: `DEFAULT_DISPLAY['poll_hz']` and `max_partial_updates_per_sec` control
	input polling and rate-limiting of partial updates to avoid over-driving the
	display or CPU.
- Partial updates are used where supported to speed responsiveness and avoid full
	refresh flicker. When drivers don't support partial updates, full updates are used.

Running the project
-------------------
The package supports both simulated and real-hardware runs. On a development machine
you'll typically run in simulation mode.

1) Create a virtualenv and install requirements

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r picker/requirements.txt
```

2) Smoke test config loader

```bash
python -m picker.config
# Should print the loaded knob keys and exit if the JSON is valid.
```

3) Run with simulation

```bash
PYTHONPATH=. python picker/run_picker.py --simulate --display-w 800 --display-h 600
```

4) Run on-device (Raspberry Pi + hardware)

Notes before running on a Pi:
- Enable SPI in `raspi-config` (Interface Options -> SPI).
- Ensure your user is in the `spi` and `gpio` groups:
	```bash
	sudo usermod -aG spi,gpio $USER
	# Log out and back in for changes to take effect
	```
- Install platform-specific extras:
	- **Raspberry Pi 5**: The standard `RPi.GPIO` library is not supported. Use `rpi-lgpio` instead:
		```bash
		pip uninstall RPi.GPIO
		pip install rpi-lgpio spidev
		```
	- **Raspberry Pi 4 and earlier**:
		```bash
		pip install RPi.GPIO spidev
		```

Example (on a Pi):

```bash
# use appropriate venv with platform-specific packages installed
PYTHONPATH=. python picker/run_picker.py --display-w 1448 --display-h 1072 --display-spi-device 0
```

Calibration
-----------
- Use the interactive calibrator to produce a per-device `mcp3008_calibration.json`.

```bash
PYTHONPATH=. python picker/run_picker.py --run-calibrator --calibration my_cal.json
```

- The calibrator will guide you through moving each knob to all 12 detents and will
	output a JSON file containing per-channel voltage breakpoints. Use that file with
	`--calibration` when running the picker.

Testing
-------
- Unit tests: install pytest in your venv and run from the repo root:

```bash
source .venv/bin/activate
pytest -q picker/tests
```

- The tests use the simulated ADC and simulated display where appropriate so they
	should pass on macOS and Linux without hardware.

Developer notes and next steps
------------------------------
- The `picker/ui.py` and `picker/drivers/*` modules are intentionally modular so you
	can improve fonts, layout, or driver implementations without touching the core
	state machine.
- Suggested small improvements:
	- Add a small CLI mode to dump frames to a file for UI debugging.
	- Add an integration test that runs the core loop for a short period with simulated
		inputs to smoke-test the whole pipeline.

Security and content notes
--------------------------
- The sample data in `sample_texts.json` contains demographic categories used as
	example labels. The picker code treats these as arbitrary text values; any
	deployment that uses potentially-sensitive labels should ensure it complies with
	local policies and regulations.

Files of interest (quick map)
----------------------------
- `picker/run_picker.py` — CLI entrypoint
- `picker/config.py` — config and text loader
- `picker/hw.py` — hardware abstraction and simulation
- `picker/ui.py` — image composition
- `picker/core.py` — app state machine / event loop
- `picker/sd_client.py`, `picker/sd_config.py` — Stable Diffusion client and defaults
- `picker/drivers/` — display drivers and factory
- `picker/mcp3008_calibration.json` — sample calibration file

Contact and license
-------------------
See top-level repository `LICENSE` and project `README.md` for licensing and broader
project context.

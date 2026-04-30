# picker — Rotary-knob selection UI for e-paper displays

This repository contains the **picker** application: a compact, standalone UI
driven by six 12-position rotary knobs and two buttons, designed for headless
hardware (Raspberry Pi + MCP3008 ADC + IT8951-based e-paper display).  Full
simulation support lets you develop and test on any workstation without
connected hardware.

## What it does

- Reads six rotary knobs (CH0–CH2, CH4–CH6) and two buttons (CH3 = GO,
  CH7 = RESET) via an MCP3008-style ADC.
- Rotating any knob shows a full-screen overlay listing the 12 text values for
  that knob, with the selected item inverted/highlighted.  The overlay clears
  2 seconds after the last change.
- Pressing **GO** calls a Stable Diffusion Web UI server to generate an image
  from the currently selected knob values (supports both `txt2img` and
  `img2img` modes) and renders it on the display.
- Pressing **RESET** shows a "RESETTING" message for 2 seconds and schedules
  a full display refresh.
- Optional live MJPEG camera stream (flag `--stream`, default port 8088).

## Repository layout

```
picker/               Python package — the full application
  config.py           Config loader and defaults
  hw.py               Hardware abstraction (ADC, knob mapping, buttons)
  ui.py               Pillow-based image composition
  core.py             State machine and event loop
  sd_client.py        Stable Diffusion client (GO action)
  sd_config.py        SD constants and defaults
  run_picker.py       CLI entry point
  calibrate.py        Interactive knob calibrator
  capture_still.py    Camera capture helper (img2img mode)
  drivers/
    display_fast.py   Thread-safe display adapter (high-level API)
    epaper_enhanced.py  Driver factory: IT8951 → basic SPI → simulation
    epaper_standalone.py  Self-contained IT8951 SPI implementation
  tests/              Unit and integration tests (pytest)
  assets/             Placeholder images and HTML preview page
  systemd/            systemd drop-in templates
  mcp3008_calibration.json  Example calibration file
  sample_texts.json   Default knob label configuration
  requirements.txt    Python dependencies
IT8951/               Git submodule — IT8951 Python driver (GregDMeyer/IT8951)
setup_picker.sh       One-step setup script for Raspberry Pi
```

## Quick start

### 1 — Clone with submodules

```bash
git clone --recurse-submodules <repo-url>
# or, if already cloned:
git submodule update --init --recursive
```

### 2 — Create a virtualenv and install dependencies

**Raspberry Pi 5** (uses system-provided GPIO/SPI libraries):
```bash
python -m venv .venv --system-site-packages
source .venv/bin/activate
# Do NOT pip-install RPi.GPIO or spidev — use the system versions
```

**All other platforms** (including development on macOS/Linux):
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Python requirements and the IT8951 driver:
```bash
bash setup_picker.sh
# or manually:
pip install -r picker/requirements.txt
pip install -e IT8951/
```

### 3 — Run in simulation mode (no hardware required)

```bash
PYTHONPATH=. python picker/run_picker.py --simulate --display-w 800 --display-h 600
```

### 4 — Run on hardware (Raspberry Pi)

Enable SPI (`raspi-config` → Interface Options → SPI) and add your user to
the `spi` and `gpio` groups:

```bash
sudo usermod -aG spi,gpio $USER
# re-login for the group change to take effect
```

Run the picker:
```bash
PYTHONPATH=. python picker/run_picker.py \
    --display-w 1448 --display-h 1072 --display-spi-device 0
```

Run in `img2img` mode (requires a connected camera):
```bash
PYTHONPATH=. python picker/run_picker.py \
    --generation-mode img2img --display-w 1448 --display-h 1072
```

Enable the live camera stream:
```bash
PYTHONPATH=. python picker/run_picker.py --stream
# View at http://<pi-ip>:8088/stream.mjpg
```

**Raspberry Pi 5 note**: replace `RPi.GPIO` with `rpi-lgpio`:
```bash
pip uninstall RPi.GPIO
pip install rpi-lgpio spidev
```

## Configuration

### Knob labels — `picker/sample_texts.json`

Each knob maps to a key (`CH0`–`CH2`, `CH4`–`CH6`).  Each key has:
- `"title"`: category name shown above the overlay
- `"values"`: array of exactly 12 strings (empty string `""` leaves a slot blank)

```json
{
  "CH0": { "title": "Colour", "values": ["Red","Orange","Yellow","Green","Blue","Indigo","Violet","Black","White","Gray","Brown",""] },
  "CH1": { "title": "Size",   "values": ["XS","S","M","L","XL","2XL","3XL","4XL","5XL","6XL","7XL",""] }
}
```

Pass a custom file with `--config /path/to/my_texts.json`.

### Knob calibration

Run the interactive calibrator to produce a per-device
`mcp3008_calibration.json`:

```bash
PYTHONPATH=. python picker/run_picker.py \
    --run-calibrator --calibration my_cal.json
```

Use it when starting the picker:
```bash
PYTHONPATH=. python picker/run_picker.py --calibration my_cal.json
```

## Running tests

```bash
source .venv/bin/activate
pytest -q picker/tests
```

All tests use the simulated ADC and simulated display, so they pass without
any connected hardware on macOS and Linux.

## Systemd services

- `picker/picker_startup.service` — standard `txt2img` mode on boot
- `picker/picker_camera_still_startup.service` — `img2img` mode on boot

See `picker/README_picker_startup.md` and
`picker/README_picker_camera_still_startup.md` for installation instructions.

A systemd drop-in that prevents a boot race with `systemd-tmpfiles` (needed
for the Arducam camera tuning symlink) is in `picker/systemd/`.  Install it
with:

```bash
sudo ./picker/install_systemd_dropin.sh
```

## Troubleshooting

- **SPI / GPIO errors**: run `./picker/diagnose_epaper.sh` for a quick
  diagnostic.
- **Camera tuning (Arducam Pivariety)**: run
  `sudo ./picker/setup_camera_tuning.sh` to create the required
  `arducam-pivariety.json` symlink.
- **IT8951 ImportError**: ensure `IT8951/` is initialised
  (`git submodule update --init --recursive`) and installed
  (`pip install -e IT8951/`).
- **Partial updates not working**: try a different `--rotate` value or run
  `--force-simulation` to verify the issue is hardware-specific.

## Key CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--simulate` | off | Use simulated ADC (no hardware needed) |
| `--force-simulation` | off | Force simulated display output |
| `--config FILE` | bundled sample | Path to texts JSON |
| `--calibration FILE` | none | Path to knob calibration JSON |
| `--display-w W` | 1024 | Display width in pixels |
| `--display-h H` | 600 | Display height in pixels |
| `--display-spi-device N` | 0 | SPI CE for the e-paper display |
| `--rotate {CW,CCW,flip,none}` | CW | Rotate display output |
| `--generation-mode {txt2img,img2img}` | txt2img | SD generation mode |
| `--stream` | off | Enable live MJPEG camera stream |
| `--stream-port PORT` | 8088 | Port for the MJPEG stream |
| `--run-calibrator` | off | Run the interactive knob calibrator |
| `--verbose` | off | Enable debug logging |

## License

See `LICENSE` in this repository.


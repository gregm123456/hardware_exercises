Picker — Design, implementation, and usage
=========================================

This `picker/` package implements a small, standalone selection UI designed for
headless hardware (Raspberry Pi + e-paper display) but with simulation paths so
you can develop and test on a workstation.

Two **input modes** are supported and can be chosen at run time:

| Mode | Hardware | CLI flag |
|------|----------|----------|
| **ADC knobs** (original) | MCP3008 ADC · six 12-position rotary knobs · GO button (CH3) · RESET button (CH7) | *(default — no extra flag)* |
| **Rotary encoder** (new) | One standard rotary encoder knob with integrated pushbutton · five leads to GPIO | `--rotary` |

Both modes drive the same e-paper display and Stable Diffusion integration.

Quick summary
-------------
- **Purpose**: provide a compact UI for selecting values from configurable
  text lists and triggering image generation with Stable Diffusion.
- **Hardware**: MCP3008 ADC knobs *or* a single GPIO rotary encoder;
  SPI-based e-paper display (IT8951 / Waveshare variants); Raspberry Pi.
- **Simulation**: all hardware paths (ADC, GPIO, display) are simulated so
  you can run and test on macOS/Linux without connected hardware.

Highlights
----------
- **Original ADC knob mode**: six 12-position knobs read via MCP3008; GO and
  RESET as separate ADC-threshold buttons; per-knob calibration with hysteresis
  to avoid flicker between detents.
- **Rotary encoder mode** (new): one rotary encoder + pushbutton replaces all
  six knobs and two buttons. The encoder navigates a two-level hierarchical menu:
  rotate to scroll, press to enter/select. Menu count and item count are
  unrestricted and set in the JSON config.
- Supports both `txt2img` and `img2img` Stable Diffusion generation modes.
- **Live Stream**: MJPEG camera stream available with `--stream` (default port 8088).
- Display abstraction supports several backends: `update_waveshare`, IT8951
  Python package, basic SPI implementation, and a simulated display for
  development.
- Minimal core loop: polls HW, composes overlay images with Pillow, pushes
  frames to the display adapter.

---

Project layout and responsibilities
------------------------------------

### Top-level files (important ones)

- `run_picker.py` — CLI launcher. Handles arguments for simulation, display
  size, calibration file, and starting the interactive calibrator. Also
  handles the new `--rotary` / `--rotary-simulate` flags.
- `config.py` — loads menus/texts and provides defaults for calibration,
  display parameters, and GPIO pin assignments. Key functions:
  - `load_texts()` — validates the legacy CH-key JSON structure (each knob
    has exactly 12 values); used by the ADC knob mode.
  - `load_menus()` — accepts *both* the legacy CH-key format and the new
    flexible `menus`-list format; used by the rotary encoder mode.
- `mcp3008_calibration.json` — example calibration file produced by the
  calibrator (ADC mode only).
- `picker_startup.service` / `picker_camera_still_startup.service` —
  systemd service files for running the picker on boot.
- `README_picker_startup.md` / `README_picker_camera_still_startup.md` —
  setup instructions for the systemd services.
- `setup_camera_tuning.sh` — helper to ensure the Arducam tuning JSON is
  correctly linked. Required for `libcamera` to function with specific modules.

### Raspberry Pi 5 service notes
When running as a service on Pi 5:
- **Infinite Restarts**: Ensure your `.service` file uses
  `StartLimitIntervalSec=0` in the `[Unit]` section to allow recovery from
  hardware initialization races.
- **Python Path**: If installing in a venv with system-site-packages, set
  `Environment=PYTHONPATH=/home/<user>/hardware_exercises` in the `[Service]`
  section.
- **Tuning Files**: The Arducam tuning file (`arducam-pivariety.json`) must be
  at `/usr/share/libcamera/ipa/rpi/vc4/` (or symlinked). Use
  `picker/systemd/tmpfiles.conf` to manage this persistently across reboots.

### Core modules (`picker/`)

- `hw.py` — hardware abstraction layer (ADC knob mode).
  - `SimulatedMCP3008`: in-memory ADC simulator.
  - `Calibration` dataclass: per-knob calibration breakpoints and settings.
  - `KnobMapper`: maps raw ADC values to discrete positions (0..11) with
    hysteresis and a stability counter (debounce).
  - `HW`: high-level helper exposing `read_positions()` and `read_buttons()`.

- `rotary_encoder.py` *(new — rotary mode)* — GPIO driver for a standard
  rotary encoder knob with integrated pushbutton.
  - `RotaryEncoder`: polls GPIO at 1 kHz in a background thread; uses a
    16-entry quadrature state machine for glitch-free step detection; applies
    time-based software debounce to the pushbutton (default 50 ms).
  - `SimulatedRotaryEncoder`: event-injection simulator for tests; API-
    compatible with `RotaryEncoder`.
  - Events emitted: `('rotate', +1)` CW, `('rotate', -1)` CCW,
    `('button', True)` press, `('button', False)` release.

- `rotary_core.py` *(new — rotary mode)* — navigation state machine.
  - Two states: `TOP_MENU` and `SUBMENU`.
  - Top level shows: `["Back", menu_0_title, ..., menu_N_title, "Go", "Reset"]`.
    The cursor is always reset to `"Back"` (index 0) whenever the top menu is
    re-displayed, so the user can immediately press to return to the main screen.
  - Submenu shows: `["↩ Return", item_0, ..., item_K, ""]`.
    The currently-selected item is auto-snapped and visually marked with a
    `* ` prefix (e.g. `"* Adult"`).  The last entry `""` is a blank
    (no-selection) choice.
  - Press "Back" at top level → fires callback; press a menu name → enter
    submenu; press "↩ Return" → go back without changing selection; press an
    item or blank → save selection and return to top level.
  - Press "Go" or "Reset" at top level → fires callback.
  - `RotaryPickerCore.get_current_values()` → `{menu_title: selected_value}`.
    An index pointing at the blank entry returns `""`.

- `ui.py` — UI composition utilities (Pillow).
  - `compose_overlay(title, values, selected_index, full_screen)` — 12-item
    knob overlay with the selected item visually highlighted (ADC mode and
    rotary submenu).
  - `compose_rotary_menu(title, items, selected_index, full_screen)` *(new)* —
    variable-length list with the selected item highlighted and a proportional
    scroll indicator on the right edge when the list is longer than the visible
    window.  Used for the rotary TOP_MENU navigation list.
  - `compose_main_screen(...)` and `compose_message(...)` — full-screen
    surfaces used for both modes.

- `core.py` — picker application core (`PickerCore`): display worker thread,
  SD image generation, camera integration, main-screen composition and the
  ADC-mode event loop.  Also used internally by the rotary encoder mode to
  provide the same full application functionality.

- `sd_client.py` — Stable Diffusion Web UI client used by the GO action.

- `sd_config.py` — constants and defaults used by `sd_client` (server URL,
  `EPAPER_GAMMA`, generation parameters).

### Driver folder (`picker/drivers/`)

- `display_fast.py` — compact display adapter used by both modes; wraps a
  `create_display(...)` factory and serializes blits with a lock.
- `epaper_enhanced.py` — display factory: tries `update_waveshare` → IT8951 →
  basic SPI → `SimulatedDisplay`.
- `epaper_standalone.py` — self-contained IT8951 implementation used when
  external dependencies aren't available.

---

Configuration / JSON format
-----------------------------

### Legacy CH-key format (ADC knob mode and backward-compatible)

Used by `load_texts()` (and also accepted by `load_menus()`). Requires exactly
six channel keys (`CH0`, `CH1`, `CH2`, `CH4`, `CH5`, `CH6`) each with exactly
12 values:

```json
{
  "meta": { "version": "1.0" },
  "CH0": { "title": "Colour", "values": ["Red","Orange","Yellow","Green","Blue","Indigo","Violet","Black","White","Gray","Brown",""] },
  "CH1": { "title": "Size",   "values": ["XS","S","M","L","XL","2XL","3XL","4XL","5XL","6XL","7XL",""] }
}
```

Empty strings `""` are allowed to deliberately leave a slot blank. The bundled
`sample_texts.json` uses this format and is the default when no `--config` is
given.

### New `menus`-list format (rotary encoder mode)

Accepted by `load_menus()`. Any number of menus; each menu may have any number
of values (no fixed-length requirement). Blank strings are automatically
filtered out:

```json
{
  "menus": [
    {"title": "Colour", "values": ["Red", "Blue", "Green"]},
    {"title": "Style",  "values": ["Realistic", "Painterly", "Sketch", "Watercolour"]},
    {"title": "Subject", "values": ["Portrait", "Landscape", "Abstract"]}
  ]
}
```

Both formats can share the same JSON file. If a `"menus"` key is present,
`load_menus()` uses it; otherwise it falls back to the CH-key format.

---

Rotary encoder input mode
--------------------------

**📖 For detailed optimization techniques and performance tuning, see [ROTARY_ENCODER_OPTIMIZATION.md](ROTARY_ENCODER_OPTIMIZATION.md)**

This section covers basic rotary encoder usage. The optimization guide documents advanced techniques including queue draining, directional momentum filtering, and partial refresh implementation.

### Hardware wiring

Connect a standard incremental rotary encoder (with integrated pushbutton)
using five leads — no external resistors needed (internal pull-ups are
configured by the driver):

| Lead | GPIO (BCM) | Notes |
|------|-----------|-------|
| GND  | Ground    | Common ground |
| 3V3  | 3.3 V supply | Do not use 5 V |
| CLK (A) | 17 (default) | Configurable with `--rotary-clk` |
| DT  (B) | 18 (default) | Configurable with `--rotary-dt` |
| SW      | 27 (default) | Active-LOW; configurable with `--rotary-sw` |

**Raspberry Pi 5**: `RPi.GPIO` is not supported on Pi 5. Install `rpi-lgpio`
instead (see *Running on hardware* below).

### User interface flow

```
 ┌─────────────────────────────────────────────────────┐
 │  TOP MENU                                           │
 │  ──────────────────────────────────────────────     │
 │  ▶ Back               ← push to return to main     │  ← cursor always starts here
 │    Sex/Gender          ← rotate to highlight        │
 │    Age                 ← push to enter submenu      │
 │    Socioeconomics                                   │
 │    Politics                                         │
 │    Race                                             │
 │    Religion                                         │
 │    Go                  ← triggers generation        │
 │    Reset               ← triggers reset             │
 └─────────────────────────────────────────────────────┘

 ┌─────────────────────────────────────────────────────┐
 │  Age                                                │
 │  ──────────────────────────────────────────────     │
 │    ↩ Return            ← push to go back unchanged  │
 │    Young Adult                                      │
 │  ▶ * Adult             ← currently selected (marked with * )
 │    Middle-aged                                      │
 │    Senior                                           │
 │    ...                 (scroll indicator on right)  │
 │                        ← blank (no selection) last  │
 └─────────────────────────────────────────────────────┘
```

- **Rotate** — scroll through the visible list.
- **Push** — enter the highlighted submenu / select the highlighted item /
  trigger Go or Reset / return to top level.
- **"Back"** — first item in the top menu; the cursor always lands here when
  the top menu is (re-)displayed so the user can immediately press to return
  to the main screen without waiting for the idle timeout.
- **"↩ Return"** at the top of every submenu — go back to the top menu
  *without* changing the current selection for that category.
- **`* ` prefix** — the currently-selected value in a submenu is displayed
  with a `* ` prefix (e.g. `* Adult`) and is auto-snapped when entering
  the submenu so it is immediately highlighted.
- **Blank entry** — the last item in every submenu is an empty string, allowing
  the user to explicitly set *no selection* for that category.
- **Wrap-around is disabled** — rotating past the last item stops at the end
  (predictable boundary behaviour).

### Display behaviour

The e-paper content shown is identical to ADC-knob mode with two exceptions:

| Situation | What the display shows |
|-----------|------------------------|
| Idle (no interaction for 3 s in TOP_MENU) | **Main screen** — placeholder/generated image + currently selected values for every category, identical to ADC mode |
| TOP_MENU navigation (rotating or just entered) | **Navigation list** — rotary menu showing all category names + "Go" + "Reset", with the highlighted entry inverted |
| SUBMENU (entered a category) | **Knob overlay** — exactly the same 12-item overlay used in ADC mode for that channel, with the currently selected item inverted |
| After pressing Go | **"GO!" splash** → SD image generation starts → **main screen** updates when generation finishes (img2img: camera is captured first) |
| After pressing Reset | **"RESETTING" splash** → display reinitialised → **main screen** |

### Debouncing

| Signal | Method | Default |
|--------|--------|---------|
| Rotation | 16-entry quadrature state machine; invalid Gray-code transitions silently discarded | — |
| Button   | Time-based: raw GPIO level must be stable for `debounce_ms` before event is emitted | 50 ms |
| Polling  | Background thread at 1 kHz; safe on Pi; configurable with `--rotary-debounce-ms` | — |

### Running with rotary encoder

On hardware (default BCM pins 17/18/27):
```bash
PYTHONPATH=. python picker/run_picker.py --rotary
```

Custom GPIO pins:
```bash
PYTHONPATH=. python picker/run_picker.py --rotary \
    --rotary-clk 23 --rotary-dt 24 --rotary-sw 25 \
    --rotary-debounce-ms 30
```

Simulation (no hardware required — useful for development and CI):
```bash
PYTHONPATH=. python picker/run_picker.py --rotary-simulate
```

Custom config (flexible menus-list format):
```bash
PYTHONPATH=. python picker/run_picker.py --rotary --config my_menus.json
```

Full `--rotary` option reference:

| Flag | Default | Description |
|------|---------|-------------|
| `--rotary` | — | Enable rotary encoder mode (replaces ADC knobs) |
| `--rotary-simulate` | — | Use `SimulatedRotaryEncoder` (no GPIO; for testing) |
| `--rotary-clk BCM_PIN` | 17 | BCM GPIO pin for CLK / A output |
| `--rotary-dt  BCM_PIN` | 18 | BCM GPIO pin for DT  / B output |
| `--rotary-sw  BCM_PIN` | 27 | BCM GPIO pin for SW (pushbutton) |
| `--rotary-debounce-ms MS` | 50 | Button debounce window in milliseconds |

All existing flags (`--config`, `--display-w`, `--display-h`,
`--display-spi-device`, `--rotate`, `--force-simulation`, `--verbose`,
`--generation-mode`, `--stream`, `--stream-port`) work unchanged with
`--rotary`.

---

Running the project
-------------------

### 1. Create a virtualenv and install requirements

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r picker/requirements.txt
```

### 2. Smoke test config loader

```bash
# Legacy CH-key validation
python -m picker.config

# New menus-list format (works with any valid JSON)
python -c "from picker.config import load_menus; m = load_menus(); print(len(m), 'menus')"
```

### 3. Run with simulation (ADC knob mode)

```bash
PYTHONPATH=. python picker/run_picker.py --simulate --display-w 800 --display-h 600
```

### 4. Run with simulation (rotary encoder mode)

```bash
PYTHONPATH=. python picker/run_picker.py --rotary-simulate --display-w 800 --display-h 600
```

### 5. Run on hardware — Raspberry Pi

Before running on a Pi:
- Enable SPI in `raspi-config` (Interface Options → SPI).
- Ensure your user is in `spi` and `gpio` groups:
  ```bash
  sudo usermod -aG spi,gpio $USER
  # Log out and back in
  ```
- **Camera setup for img2img mode**: run the provided setup script for the
  Arducam Pivariety tuning symlink:
  ```bash
  chmod +x picker/setup_camera_tuning.sh
  sudo ./picker/setup_camera_tuning.sh
  ```
- Platform-specific GPIO library:
  - **Raspberry Pi 5**:
    ```bash
    pip uninstall RPi.GPIO
    pip install rpi-lgpio spidev
    ```
  - **Raspberry Pi 4 and earlier**:
    ```bash
    pip install RPi.GPIO spidev
    ```

ADC knob mode on Pi:
```bash
PYTHONPATH=. python picker/run_picker.py \
    --display-w 1448 --display-h 1072 --display-spi-device 0
```

Rotary encoder mode on Pi (default pins):
```bash
PYTHONPATH=. python picker/run_picker.py --rotary \
    --display-w 1448 --display-h 1072 --display-spi-device 0
```

img2img mode (captures camera still on each GO press):
```bash
PYTHONPATH=. python picker/run_picker.py --generation-mode img2img \
    --display-w 1448 --display-h 1072
```

**Troubleshooting**: run the diagnostic script if display connectivity fails:
```bash
./picker/diagnose_epaper.sh
```

---

Running as a System Service
---------------------------

The picker can be run as a systemd service to start automatically on boot. Two service files are provided:

- `picker_startup.service`: Standard mode with optional live stream.
- `picker_camera_still_startup.service`: `img2img` mode (captures camera still on GO).

### Switching Input Interfaces (Rotary vs. Knobs)

The services can be toggled between the **single rotary encoder** interface and the **six-knob (ADC)** interface by modifying the `ExecStart` command in the service file.

1.  **Edit the active service file**:
    ```bash
    sudo nano /etc/systemd/system/picker_camera_still_startup.service
    # OR
    sudo nano /etc/systemd/system/picker_startup.service
    ```
2.  **Modify the interface flag**:
    - **To use the Rotary Encoder**: Ensure `--rotary` is present in the `ExecStart` line.
    - **To use the Six Knobs (ADC)**: Remove the `--rotary` flag from the `ExecStart` line.
3.  **Apply changes**:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart picker_camera_still_startup  # or picker_startup
    ```

For detailed installation instructions, see [README_picker_startup.md](README_picker_startup.md) and [README_picker_camera_still_startup.md](README_picker_camera_still_startup.md).

---

Live camera streaming
---------------------
The picker supports a live MJPEG stream of the camera view in parallel with
operation. Works with both input modes.

Enable the stream:
```bash
PYTHONPATH=. python picker/run_picker.py --stream
# Or with rotary encoder:
PYTHONPATH=. python picker/run_picker.py --rotary --stream
```

View the stream:
- Direct link: `http://<RASPBERRY_PI_IP>:8088/stream.mjpg`
- Interactive preview: open `picker/stream_preview.html` in a browser and
  enter the Pi's IP address.

Embed in an HTML page:
```html
<img src="http://<RASPBERRY_PI_IP>:8088/stream.mjpg" width="512" height="512">
```

---

Calibration (ADC knob mode only)
---------------------------------
Use the interactive calibrator to produce a per-device `mcp3008_calibration.json`:

```bash
PYTHONPATH=. python picker/run_picker.py --run-calibrator --calibration my_cal.json
```

The calibrator guides you through all detents for each knob and writes a JSON
file with per-channel voltage breakpoints. Use that file with `--calibration`
when running the picker in ADC knob mode.

The rotary encoder does not require calibration — the quadrature state machine
handles reliable step detection regardless of the specific encoder hardware.

---

Tests and development
---------------------
Install pytest and run all unit tests from the repo root:

```bash
source .venv/bin/activate
pytest -q picker/tests
```

Test files:

| File | What it covers |
|------|----------------|
| `test_hw_mapping.py` | `KnobMapper` mapping, hysteresis, `SimulatedMCP3008` |
| `test_ui.py` | `compose_overlay` (size and visual selection sampling) |
| `test_gamma.py` | Gamma-correction logic for SD image processing |
| `test_gamma_integration.py` | Gamma integration with `sd_client.generate_image()` |
| `test_rotary.py` | `SimulatedRotaryEncoder` event injection; `RotaryPickerCore` navigation state machine (TOP_MENU / SUBMENU); `load_menus()` both formats; `compose_rotary_menu()` rendering |
| `test_rotary_picker_integration.py` | Rotary ↔ `PickerCore` bridge: `ch_by_menu_idx` mapping; `_sync_hw_from_rotary` inversion and mapper state; `_do_display` TOP_MENU vs SUBMENU branching; `_do_action` Go/Reset delegation; idle-timeout guard conditions |

All tests use simulated hardware (no physical ADC, GPIO, or display required)
and should pass on macOS and Linux.

---

Design and implementation details
----------------------------------

### 1 — Knob mapping and stability (ADC mode)

- Each knob is read via the MCP3008 ADC (0..1023 default). `KnobMapper`
  converts raw ADC values to a normalized voltage and maps it to one of 12
  discrete positions.
- Per-knob calibration allows asymmetrical or non-linear breakpoints. The
  calibrator measures voltages for each detent and stores per-channel voltage
  breakpoints in a JSON calibration file.
- Hysteresis: mapping thresholds use midpoints between calibrated positions.
  A stability counter (`stable_required`) forces N consecutive maps to the same
  value before reporting a change, preventing oscillation on noisy hardware.

### 2 — Rotary encoder step detection (rotary mode)

- A 16-entry full-step quadrature table (`_STEP_TABLE` in `rotary_encoder.py`)
  maps each 2-bit → 2-bit AB transition to `+1`, `−1`, or `0`. Transitions
  that would require jumping more than one state (electrical glitches) always
  map to `0` and are silently discarded.
- A background thread polls both GPIO pins at 1 kHz. This is fast enough to
  catch all detents while being light enough for continuous operation on a Pi.
- The button uses a separate time-based debounce: the raw GPIO level must stay
  stable for at least `_MIN_DEBOUNCE_S` (1 ms minimum, default 50 ms) before a
  press or release event is emitted. Only the *press* transition triggers
  navigation in `RotaryPickerCore`.

### 3 — Rotary mode ↔ PickerCore bridge

The rotary encoder mode uses `RotaryPickerCore` purely for navigation input
(rotate/press events) and delegates all application logic to the same
`PickerCore` instance used by ADC mode.  The bridge in `_run_rotary()` works
as follows:

1. **Shared `HW` instance** — a `SimulatedMCP3008` is created and wired into
   a standard `HW` object.  `PickerCore` reads knob positions through this
   interface normally.
2. **`_sync_hw_from_rotary()`** — whenever a submenu selection is saved, the
   rotary item index is translated to an ADC display position using the same
   inversion formula that `PickerCore` applies
   (`adc_pos = (N-1) - item_idx`, default N=12) and injected directly into the
   `SimulatedMCP3008` channel and the `KnobMapper` state, bypassing debounce
   so the change is visible immediately.
3. **`_do_display` branching** — the `RotaryPickerCore.on_display` callback
   checks the current navigation state:
   - `TOP_MENU` → enqueues a `compose_rotary_menu` image (navigation list).
   - `SUBMENU` → enqueues a `compose_overlay` image for the relevant ADC
     channel (identical to the ADC-mode knob overlay).
4. **`_do_action` delegation** — "Back" calls `picker_core.show_main()` to
   return immediately to the main screen. "Go" calls `picker_core.handle_go()`
   and "Reset" calls `picker_core.handle_reset()`, providing full SD
   generation, camera capture, img2img, display reinitialization, and
   main-screen redraw.
5. **Idle timeout (3 s)** — after 3 seconds of no encoder activity while in
   `TOP_MENU`, `picker_core.show_main()` is called to return the display to the
   main screen, mirroring the ADC-mode overlay timeout.

### 3 — Display abstraction and updates

- The display factory tries the most capable driver available:
  `update_waveshare` → IT8951 → basic SPI → `SimulatedDisplay`.
- `display_fast.py` exposes a global display instance behind a lock to
  serialize updates and reinitializations.
- Simulation mode writes frames to `/tmp/picker_display` as PNG files.

### 4 — Image handling (Stable Diffusion + e-paper)

- `txt2img` mode: selected values construct a prompt for generation.
- `img2img` mode: GO captures a camera still then sends it with the prompt.
- `_apply_gamma(img, gamma)` brightens midtones for monochrome e-paper.
  Default gamma is `sd_config.EPAPER_GAMMA` (1.8).

### 5 — Performance

- ADC mode poll rate: `DEFAULT_DISPLAY['poll_hz']` (80 Hz default).
- Rotary encoder poll: 1 kHz background thread (separate from display loop).
- Display rate-limiting: `max_partial_updates_per_sec` caps display writes to
  avoid over-driving e-paper.

---

Systemd drop-in for tmpfiles (required on some Pi setups)
----------------------------------------------------------
On some systems, libcamera may attempt to load camera tuning files before
`systemd-tmpfiles` has fully created symlinks, causing a boot race. A systemd
drop-in (`Requires=systemd-tmpfiles-setup.service`) resolves this:

Files:
- `picker/systemd/tmpfiles.conf` — drop-in template
- `picker/install_systemd_dropin.sh` — helper installer

Installation:
```bash
chmod +x picker/install_systemd_dropin.sh
sudo ./picker/install_systemd_dropin.sh
sudo systemctl status picker_camera_still_startup.service --no-pager
```

---

Security and content notes
---------------------------
The sample data in `sample_texts.json` contains demographic categories used as
example labels. The picker code treats these as arbitrary text values; any
deployment that uses potentially-sensitive labels should ensure it complies with
local policies and regulations.

---

Files of interest (quick map)
------------------------------
| File | Purpose |
|------|---------|
| `picker/run_picker.py` | CLI entrypoint (both modes); `_run_rotary` bridges rotary encoder to full `PickerCore` |
| `picker/config.py` | Config loader: `load_texts()` and `load_menus()` |
| `picker/hw.py` | ADC hardware abstraction and simulation |
| `picker/rotary_encoder.py` | GPIO rotary encoder driver + `SimulatedRotaryEncoder` |
| `picker/rotary_core.py` | Rotary navigation state machine |
| `picker/ROTARY_ENCODER_OPTIMIZATION.md` | **Detailed guide to rotary encoder optimizations and performance tuning** |
| `picker/ui.py` | Image composition: `compose_overlay`, `compose_rotary_menu`, `compose_main_screen`, `compose_message` |
| `picker/core.py` | App state machine / event loop and `PickerCore` (used by both ADC and rotary modes) |
| `picker/sd_client.py`, `picker/sd_config.py` | Stable Diffusion client and defaults |
| `picker/drivers/` | Display drivers and factory |
| `picker/setup_camera_tuning.sh` | Arducam Pivariety camera tuning symlink setup |
| `picker/mcp3008_calibration.json` | Sample calibration file (ADC mode) |
| `picker/sample_texts.json` | Sample menu configuration (CH-key format) |
| `picker/tests/test_rotary.py` | Rotary encoder and navigation state machine unit tests |
| `picker/tests/test_rotary_picker_integration.py` | Rotary ↔ PickerCore bridge integration tests |
| `picker/tests/test_hw_mapping.py` | ADC knob mapping tests |

---

Contact and license
--------------------
See the top-level repository `LICENSE` and project `README.md` for licensing
and broader project context.

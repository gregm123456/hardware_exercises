> **Status note**: The original six-knob ADC design has been fully implemented.
> An alternative single GPIO rotary encoder + pushbutton input mode has also been
> implemented (see `picker/rotary_encoder.py`, `picker/rotary_core.py`, and the
> `--rotary` CLI flag in `picker/run_picker.py`).  Refer to `picker/README.md`
> for current usage, wiring, configuration, and operation documentation.

Design constraints and assumptions
--------------------------------
- The UI must be non-blocking: drawing and state transitions run on an event loop/value-polling loop with lightweight timers.

Configuration format (new requirement)
------------------------------------
- All text values, category titles, and per-knob labels must be stored in a JSON configuration file. The JSON file allows the `picker/` package to be shipped and configured without code changes.
- Structure (example; see `picker/sample_texts.json` below):
	- Top-level object with one entry per knob key (e.g., "CH0", "CH1", "CH2", "CH4", "CH5", "CH6").
	- Each knob object contains:
		- "title": string (category title, shown above the 12-value overlay)
		- "values": array of exactly 12 strings; entries may be the empty string "" to deliberately leave a slot blank
	- Optionally include a top-level "display" or "meta" object for layout choices (font size overrides, reserved image area size), and a "calibration" object for per-channel adc_min/adc_max/inverted/hysteresis defaults.
- Example small snippet:

	{
		"CH0": { "title": "Colour", "values": ["Red","Orange","Yellow","Green","Blue","Indigo","Violet","Black","White","Gray","Brown",""] },
		"CH1": { "title": "Size", "values": ["XS","S","M","L","XL","2XL","3XL","4XL","5XL","6XL","7XL",""] }
	}

File layout (in `picker/`)
-------------------------

# Picker application — design & build plan

Purpose
-------
This document specifies the design and implementation plan for a standalone `picker` application that reads six 12-position rotary knobs (CH0, CH1, CH2, CH4, CH5, CH6) and two pushbuttons (CH3 = GO, CH7 = RESET) via an MCP3008-like ADC and drives an e-paper display to show a fast, transient menu overlay.

High-level behaviour (requirements)
----------------------------------
- Each of the six knobs selects one of 12 text values. The app must map analog readings to discrete positions (0..11).
- When any knob position changes, show a generous full-overlay menu listing the 12 text values for that knob with the currently selected item visually inverted/highlighted. After 2 seconds of no further changes, the overlay must clear.
- CH3 (GO): when pressed, display a large "GO!" on the screen for 2 seconds. (Future: fetch a 512×512 image from an API and render it above the knob values; for now reserve that area.)
- CH7 (RESET): when pressed, display "RESETTING" for 2 seconds. Also schedule any queue/flags for a full restore if needed (functionality to be implemented later).
- CH7 (RESET): when pressed, display "RESETTING" for 2 seconds. Also schedule any queue/flags for a full restore if needed (functionality to be implemented later).
- The e-paper panel is physically mounted rotated 90° clockwise. All UI rendering must account for this (either by rotating composed bitmaps before sending them to the display driver or by using a driver rotation setting); this is a display-orientation concern and does not change knob semantics.
- Knob rotation mapping (separate concern): by default interpret a clockwise rotation of a knob (as viewed from the knob face) as increasing the selection index. Per-channel calibration includes an `inverted` flag so a particular knob can be flipped in software if the mechanical wiring makes clockwise correspond to a decrease.
- Display updates must be as fast as possible. We will favour partial/fast updates and accept that occasional full refreshes (performed explicitly by RESET or maintenance) are required to retain visual integrity.

Design constraints and assumptions
--------------------------------
- Use existing project utilities (knob watchers, Waveshare/IT8951 helpers) as references, but duplicate and adapt only the minimal pieces into `picker/` so `picker/` is standalone and runnable without the rest of the repo. The plan requires each dependency used by `picker/` to either be vendor-agnostic (pypi) or copied into `picker/drivers/` with minimal API.
- Hardware: MCP3008-style ADC; knobs produce near-circular 0..1023 (or 0..4095) analog span. Provide an easy-to-configure calibration (per-channel min/max/rotation-direction) in `picker/config.py`.
- E-paper: use IT8951 or Waveshare fast partial update APIs. If both exist in the repo, copy the small fast-update helper code into `picker/drivers/display_fast.py` with a tiny abstraction layer.
- Knob/ADC reads will be debounced and quantized with hysteresis to avoid flicker.
- The UI must be non-blocking: drawing and state transitions run on an event loop/value-polling loop with lightweight timers.

Contract (tiny)
---------------
- Inputs: periodic ADC samples for CH0..CH7; config data (text lists for each knob, calibration values); button press events.
- Outputs: epaper updates (fast partial writes preferred); logs and metrics for latency and errors.
- Error modes: noisy ADC readings (hysteresis handles); display update failure (retry a limited number of times and fallback to full update); missing image in GO flow (placeholder and error state display).
- Success: User rotates a knob and within target latency the overlay updates showing the invert selection; after 2s overlay disappears; pressing GO or RESET shows their messages for 2s.

Performance targets
-------------------
- Display latency target: 120 ms or lower from a knob position change to visible update. Achieve by:
	- Poll ADC at 60–120 Hz (configurable), map values to positions, and only update display on position change.
	- Use fast partial update routines and limit redraw area to the overlay region.
	- Minimize drawing complexity: single-bit fonts, pre-rendered glyphs, single-frame delta blits.
- CPU/memory: run on a Pi-class board comfortably; avoid heavy Python image libraries at runtime (Pillow permitted for offline rendering or precompute assets).

HW mapping and calibration
--------------------------
- Channels used: CH0, CH1, CH2, CH4, CH5, CH6 = knobs; CH3 = GO button; CH7 = RESET button.
- Calibration: `picker/config.py` will contain per-channel entries:
	- adc_min, adc_max (for full travel)
	- inverted boolean (if knob direction needs inversion)
	- positions = 12
	- tolerance/hysteresis (eg 1.5% of full-scale)
- Mapping algorithm:
	- Normalize ADC: v_norm = (adc - adc_min) / (adc_max - adc_min)
	- If inverted: v_norm = 1.0 - v_norm
	- pos_f = v_norm * positions
	- pos = floor(pos_f) clipped to [0, positions-1]
	- Apply hysteresis: only accept pos change if pos remains stable for N consecutive polls or if pos crosses a threshold distance (>1 position) to make UI snappy. Use a small time debounce (e.g., 50–100 ms) plus hysteresis window.

Buttons
-------
- Read CH3 and CH7 as digital (ADC thresholds). Implement debounce and short/long press detection (long press reserved for future features). For now: short press triggers the 2s message.

UI / Rendering plan
-------------------
- Layout:
	- Reserve a 512×512 area at the top-middle for future image (or constrain to screen dimensions if smaller). For current app, render the 12-item list below or inside the area depending on display resolution.
	- The overlay shows all 12 items in a generous list. The selected item is inverted (white-on-black if display background is black-on-white) and slightly larger or bolded to increase legibility.

	- Prefer using the full screen for the overlay and messages when possible. Readability is the primary goal: do not be stingy with space. If a 512×512 image area is required, allow an alternate layout that places the 12-item list below or compressed to fit, but prefer full-screen text for the default picker overlay and GO/RESET messages.
- Rendering optimizations:
	- Pre-render text bitmaps for the 12 labels per knob on startup, scaled to the desired font size. This avoids live font rasterization on each change.
	- Use a small framebuffer representing overlay area only. When selection changes, only send the changed rows/rect to the display.
	- Implement a double-buffer diff step when possible: compute differences between previous overlay buffer and current overlay buffer and send only the changed rectangles.
	- Use e-paper fast-update modes (IT8951 partial, Waveshare LUT for fast partial). Provide an abstraction `picker/drivers/display_fast.py` with functions: init(), blit(rect, bitmap), partial_update(rect), full_update().
- Visual timing:
	- On first change after inactivity: render overlay and show immediately.
	- If further changes occur within 2s window, reset the 2s timer and update overlay accordingly.
	- When timer expires, clear overlay by drawing the background only (fast partial update) or minimal region change.

State machine & core loop
-------------------------
- States: IDLE, OVERLAY_VISIBLE (with timeout), GO_SHOWN (2s), RESET_SHOWN (2s)
- Main loop:
	- Poll ADC channels at configured rate. Map to positions. If any knob's position changed, publish event into state machine.
	- If GO or RESET pressed, immediately show their screens (overlaid full-screen or large centered text) for 2s; these override overlay display until timeout.
	- The overlay's visibility timeout resets with each knob change.
	- All timers are non-blocking; drawing operations should be scheduled asynchronously or on a short worker thread to avoid blocking ADC polling.

File layout (in `picker/`)
-------------------------
- `picker/__init__.py` — package init
- `picker/config.py` — default knob labels, calibration template, display parameters, poll rates, and performance tuning knobs
 - `picker/sample_texts.json` — full sample text configuration (category titles + 12-value arrays for each knob). This file is the canonical example used by `picker/config.py` when no external JSON is provided.
- `picker/hw.py` — hardware abstraction: ADC reader, knob->position mapping, button detection. Provide a simulation mode (fake ADC values) for development.
- `picker/ui.py` — high-level rendering primitives: overlay composition, selection inversion, GO/RESET big screens, image placeholder area.
- `picker/drivers/display_fast.py` — small, local display adapter that uses either IT8951 or Waveshare fast partial APIs (duplicated/trimmed from repo), exposing minimal fast blit/partial_update/full_update functions.
- `picker/core.py` — state machine, event loop, timers, glue between `hw` and `ui`.
- `picker/run_picker.py` — CLI runner. Flags: --simulate, --log-level, --config <file>, --no-display (headless test mode).
- `picker/README.md` — short doc and run steps.
- `picker/tests/` — unit tests for mapping and a small simulation of UI timing.

Standalone requirement (important)
--------------------------------
The `picker` directory must be runnable on its own. To satisfy that requirement we will:
- Copy only the minimal fast-display helper code into `picker/drivers/display_fast.py` and adapt imports. Keep copyright headers.
- Copy or re-implement small ADC utilities if the rest of the repo centralises them; prefer a minimal `MCP3008Reader` shim that can either use spidev or a simulated read function.
- Keep external dependencies minimal and declare them in `picker/requirements.txt` (Pillow optional, typed-args, python-dateutil, etc.).

Testing and verification
------------------------
- Unit tests:
	- ADC-to-position mapping (happy path and edge-case: min/max and noisy center)
	- Hysteresis behaviour test (simulate jitter and ensure no flicker)
	- Timer semantics (overlay visible for 2s after last change)
- Integration tests (simulated hardware): run `run_picker.py --simulate` and exercise knobs/buttons. Provide automated script to advance simulated ADC values and assert UI events are scheduled.

Edge cases and mitigations
-------------------------
- Noisy ADC: use hysteresis + debounce + consecutive-read confirmation.
- Rapid knob sweeps: if the user spins through multiple positions quickly, ensure the UI updates remain fluid and do not trigger too many heavy display writes — throttle redraw to a sane rate (e.g., 20–30 updates/sec max), while keeping apparent responsiveness. Use a small adaptive coalescing window (e.g., 30–50 ms) to debounce rapid sequences.
- Display failure: if the partial update API errors repeatedly, fallback to full update once and then mark display degraded until manual RESET.

Implementation steps (ordered)
-----------------------------
1. Create package skeleton and `picker/config.py` with default labels and calibration template. (Small, 10–20m)
2. Implement `picker/hw.py` with simulation mode and ADC->position mapping + tests. (1–2h)
3. Create `picker/drivers/display_fast.py` by extracting the minimal fast-update code and exposing the small abstraction. Add an adapter for simulation mode that writes bitmaps to disk. (1–2h)
4. Implement `picker/ui.py`: pre-render text bitmaps, overlay composer, diffing logic, and a thin API for GO/RESET screens. (2–3h)
5. Implement `picker/core.py` with state machine, timers, and integration. (2h)
6. Write `picker/run_picker.py` with CLI flags and simulate mode and test manually on hardware. (30–60m)
7. Add unit tests and a small README with run and tuning steps. (1h)

Acceptance criteria
-------------------
- Rotating any knob shows the 12-item overlay with the selected entry inverted. The overlay clears 2 seconds after the last change.
- Pressing CH3 (GO) shows a large "GO!" message for 2 seconds; pressing CH7 shows "RESETTING" for 2 seconds.
- The app runs in `--simulate` mode without physical hardware.
- The `picker/` folder contains all necessary minimal drivers so it runs standalone (dependencies listed in `picker/requirements.txt`).

Next steps and follow-ups
------------------------
- I'll start the implementation from the todo list next: `hw.py` first (simulate-capable ADC reading and mapping). After that I'll implement the display adapter and UI.
- Future extensions: image fetching and rendering for GO flow, long-press actions, a persistent settings UI, and a web API for remote control.

Notes
-----
- Keep performance measurements (latency from knob movement to visible update) in logs for initial tuning.
- For the critical fast updates, test both IT8951 and Waveshare fast update code paths on hardware; choose the fastest reliable LUT/mode.

- UI/readability note: whenever practical, use the display's full resolution for picker overlays and big-status messages (GO/RESET). Reserve the image area only when an actual image is being displayed or when the UI configuration explicitly requests a compact layout.

End of plan


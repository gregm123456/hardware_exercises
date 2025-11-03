Picker rotation and portrait-mode documentation
=============================================

This document explains how the `picker/` subproject supports composing and
displaying portrait-oriented content on displays that are physically mounted in
landscape (or otherwise rotated). It covers the two-stage approach used by the
codebase (compose-time layout and send-time rotation), where to configure the
behavior, and recommended changes / troubleshooting tips.

Overview (short)
-----------------
- The picker composes UI images with Pillow and can target either a logical
  portrait canvas or the physical display dimensions. To support displays that
  are mounted rotated (e.g., a portrait layout shown on a landscape display),
  the project uses two cooperating steps:
  1. Compose-time: the core swaps width/height so the UI is laid out as
     portrait (narrow/tall).
  2. Send-time: right before writing to the hardware, the final bitmap is
     rotated so the physical display receives a landscape-sized image whose
     internal content appears portrait.

Why two layers?
----------------
- Composing in the logical (portrait) coordinate space keeps layout code
  simple — fonts, alignment and placeholder areas behave as if the display
  were physically portrait.
- Rotating at the final step ensures the bitmap matches the display's pixel
  orientation (width x height) while preserving the intended portrait
  appearance. This approach avoids changing layout math throughout the UI and
  centralizes the hardware-oriented transform.

How to enable rotation (CLI / programmatic)
------------------------------------------
- CLI flag: `run_picker.py --rotate` accepts: `CW`, `CCW`, `flip`, or `none`.
  - Example: PYTHONPATH=. python picker/run_picker.py --rotate CW --display-w 1024 --display-h 600
- Programmatic: when creating `PickerCore`, pass `rotate='CW'|'CCW'|'flip'|None`.
  - Example: core = PickerCore(hw, texts, display_size=(1024,600), rotate='CW')
- `blit()` also accepts a `rotate` argument to apply rotation for a single frame.

Key code locations and what they do
-----------------------------------
1) PickerCore.__init__ (picker/core.py)
   - Parameter: rotate (default 'CW' via CLI unless set to 'none').
   - Behavior: If rotate is `'CW'` or `'CCW'`, sets
     `self.effective_display_size = (display_size[1], display_size[0])` — i.e.
     swap width/height. The rest of the UI composition uses
     `self.effective_display_size` so overlays and the main screen are laid out
     in portrait coordinates.

2) compose_main_screen (picker/ui.py)
   - Signature: compose_main_screen(texts, positions, full_screen=(W,H), rotate_output=None, ...)
   - Behavior:
     - If the supplied `full_screen` is landscape (W > H), the function may
       compose on a portrait canvas (swapping layout dims internally) and set
       `auto_rotated=True` so it can later rotate the result back.
     - There is an additional convenience parameter `rotate_output` that,
       when provided, rotates the returned PIL Image by CW/CCW/flip.
   - Note: In normal `PickerCore` flow the composer receives the already-swapped
     `effective_display_size` so it composes portrait content directly. The
     `rotate_output` parameter is independent and intended for callers who want
     the composed image file saved with a rotation.

3) blit (picker/drivers/display_fast.py)
   - Signature: blit(full_bitmap, file_label='frame', rotate=None, mode='auto')
   - Behavior: If `rotate` is provided, `blit` applies the rotation to
     `full_bitmap` before sending it to the hardware driver. Implemented as:
     - `'CW'`  -> `img.rotate(-90, expand=True)`
     - `'CCW'` -> `img.rotate(90, expand=True)`
     - `'flip'` -> `img.transpose(Image.FLIP_LEFT_RIGHT)`
   - The rotated image is then passed to the display driver via
     `_display.display_image(...)`.

4) run_picker.py (CLI glue)
   - Parses `--rotate` and passes the chosen value into both `PickerCore`
     and the initial `blit()` calls used for startup messages. The CLI maps
     `--rotate none` to `rotate=None` so you can disable rotation entirely.

Typical portrait workflow (what happens step-by-step)
---------------------------------------------------
1. The user requests rotation (e.g., `--rotate CW`).
2. `PickerCore` swaps `effective_display_size` so the UI code composes in
   portrait layout.
3. UI composers (`compose_overlay`, `compose_main_screen`) produce a portrait
   image sized to `effective_display_size`.
4. When the frame is enqueued, `PickerCore` passes `self.rotate` into `blit`.
5. `blit` rotates the portrait image by -90° (CW) so the final bitmap has the
   display's landscape dimensions but portrait-oriented contents.
6. Display driver writes the rotated bitmap to the hardware.

Notes and caveats
-----------------
- Double rotation in `compose_main_screen`: the function supports both an
  internal `auto_rotated` path and a user-facing `rotate_output`. If you
  both compose with swapped dimensions and pass `rotate_output`, you may see
  multiple rotations. In normal `PickerCore` usage this is not necessary;
  `PickerCore` relies on `blit()` to perform the final rotation for hardware.
- `display_fast.init(..., rotate=...)` accepts a `rotate` parameter but does
  not act on it in the current implementation — rotation is applied per-blit.
- Use `--rotate none` to disable any rotation transforms so the composed image
  is sent to hardware as-is. This is useful for debugging or displays that are
  already mounted in the intended orientation.

Recommended small refactors (optional)
-------------------------------------
- Simplify rotation handling by centralizing it in `blit()` only:
  - Remove `rotate_output` and internal `auto_rotated` rotation from
    `compose_main_screen` and document that `blit()` is the single point of
    truth for physical rotation.
  - Keep `PickerCore` swapping `effective_display_size` to keep composition
    logic portrait-friendly; `blit()` will convert to the display's pixel
    orientation before sending.
- Alternatively, make `compose_main_screen` always compose in the exact
  `full_screen` passed (no auto-rotation) and let callers compute swapped
  `full_screen` if they want portrait layout. This makes `compose_main_screen`
  behavior simpler and shifts responsibility to the caller.

Troubleshooting
---------------
- If UI text or placeholder is clipped:
  - Confirm whether `effective_display_size` is the intended size. If you
    passed `--rotate CW`, the composed canvas will be swapped. Try
    `--rotate none` to see the composition at the physical dimensions.
- If icons/text appear sideways on hardware but look correct in saved PNGs:
  - Ensure `blit` received the expected `rotate` argument. `PickerCore` passes
    `self.rotate` to `blit`, but a direct `blit(..., rotate=None)` call will
    send unrotated bitmaps.
- If you see unexpected double-rotated outputs when saving PNGs
  (compose_main_screen used with `rotate_output` and also `blit` rotate):
  - Avoid using `rotate_output` in `compose_main_screen` and rely on `blit`.

Code snippets (reference)
-------------------------
- PickerCore swap (core.py):
  if rotate in ('CW', 'CCW'):
      self.effective_display_size = (display_size[1], display_size[0])

- compose_main_screen rotation (ui.py):
  if auto_rotated:
      img = img.rotate(-90, expand=True)
  if rotate_output == 'CW':
      img = img.rotate(-90, expand=True)

- blit rotation (drivers/display_fast.py):
  if rotate == 'CW':
      img_to_send = full_bitmap.rotate(-90, expand=True)

Examples
--------
- Portrait display mounted rotated clockwise on a landscape panel:
  PYTHONPATH=. python picker/run_picker.py --rotate CW --display-w 1024 --display-h 600

- Disable rotation entirely (compose & display same orientation):
  PYTHONPATH=. python picker/run_picker.py --rotate none --display-w 1024 --display-h 600

Further help
------------
If you want, I can:
- Create a small demo script that generates one composed portrait PNG and the
  final rotated PNG (so you can visually compare compose vs. sent frame).
- Remove `rotate_output`/`auto_rotated` redundancy from `compose_main_screen`
  and run tests to ensure nothing else changes.

Finished — the rotation behavior is intentionally simple: compose portrait by
swapping dims, rotate at send time. If you want I can implement the small
refactor to centralize rotation into `blit()` and simplify composers.

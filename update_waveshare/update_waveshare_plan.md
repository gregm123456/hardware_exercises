# Update Waveshare — Implementation Plan

Purpose
-------
This document is a short coding plan for a small Python utility package `update_waveshare` that will provide functions to update a Waveshare/IT8951 e-paper display with an image file. The plan outlines the package API, implementation approach, partial-refresh strategy, tests, and a step-by-step development checklist. We'll review this plan before I create any code.

Requirements (extracted)
------------------------
- Provide a Python importable package in `update_waveshare/`.
- Accept a common image file as input and update the Waveshare display with it.
- Support partial refreshes.
- Provide a method/function to blank the screen.
- Methods must be usable from other Python code with `import`.
- Use `blank_screen.py` and examples in `IT8951/` as references.

Assumptions
-----------
1. The repository already contains an `IT8951` package with display classes (see `IT8951/display.py`) which we will import and call.
2. We'll require Pillow (`PIL`) to load and manipulate images.
3. The package should work both with the real device (using `IT8951.display.AutoEPDDisplay`) and a virtual display (`IT8951.display.VirtualEPDDisplay`) like the repo's examples.
4. Partial-refresh support can be implemented either by:
   - accepting both the current (previous) image and the new image and computing diffs, or
   - maintaining an internal cache of the last-displayed image for delta computation.
   We'll implement both options so callers can choose.

High-level design / API contract
--------------------------------
The package will expose a small, explicit API from `update_waveshare/__init__.py` (or `update_waveshare/core.py`):

- display_image(image_path: str, *, device=None, mode: str = 'auto', prev_image_path: Optional[str] = None, bbox: Optional[Tuple[int,int,int,int]] = None, vcom: float = -2.06, rotate: Optional[str] = None, mirror: bool = False, virtual: bool = False) -> None
  - Inputs: path to an image file (png/jpeg/etc). Optional device instance or device options to create one.
  - Behavior: load image, convert to device format if needed, perform a full update or partial update depending on `mode` and provided arguments.
  - `mode` values: `full` (always full refresh), `partial` (attempt partial update), `auto` (compute diff and pick partial if small region).
  - If `prev_image_path` is provided, compute diff between prev and new; otherwise use internal cache if available; else fall back to full refresh.

- partial_refresh(prev_img: PIL.Image.Image, new_img: PIL.Image.Image, *, threshold: int = 5, max_regions: int = 4) -> List[Tuple[int,int,int,int]]
  - Returns a list of bounding boxes to update. Uses a simple difference and merges nearby regions.

- blank_screen(*, device=None, vcom: float = -2.06, rotate: Optional[str] = None, mirror: bool = False, virtual: bool = False) -> None
  - Clear the display (white or black depending on device semantics) using the `IT8951` API similarly to `blank_screen.py`.

- helper: _create_device(vcom, rotate, mirror, virtual) -> device instance
  - Factory to create either `AutoEPDDisplay` or `VirtualEPDDisplay` from `IT8951.display`.

Data shapes / outputs
---------------------
- Input images: any format Pillow supports.
- Device object: whatever `IT8951.display` provides (we'll import and use it internally).
- Error modes: raises exceptions for missing files, unsupported images, or device errors.
- Success: returns None (side-effect: display is updated). Optionally can return metadata (regions updated) if caller requests it.

Partial-refresh strategy & trade-offs
-------------------------------------
Options:
- Require caller to pass both current (previous) and new images. This is stateless and straightforward.
- Maintain an internal cached image of the last image displayed by the package. This is convenient for simple scripts but can get out of sync if other code updates the display.

Planned approach (both):
- API accepts `prev_image_path` or `prev_image` (PIL Image) to compute diffs.
- If not provided, the package will look for an internal (per-process) cache file in `~/.cache/update_waveshare/last_display.png` (configurable) and use it if present.
- If no previous image is available, fall back to full refresh.

Difference algorithm (simple and fast):
1. Convert both images to the same size and greyscale format matching device resolution.
2. Compute pixel-wise absolute difference.
3. Threshold the diff to a binary mask (threshold parameter).
4. Extract connected components (or bounding boxes from runs) and merge nearby boxes up to `max_regions` boxes.
5. For each bounding box, prepare a cropped image and issue a partial update call via the device API.

Notes about hardware API
------------------------
- The exact partial update API depends on `IT8951.display`. We'll inspect it before implementing. Common patterns:
  - `display.display(image)` — full refresh
  - `display.display_partial(image, x, y, w, h)` — partial refresh
- During implementation we'll check available methods and adapt. If the underlying driver lacks a direct partial-update method, we will emulate it by composing a full buffer and instructing a hardware partial update if supported, or else fall back to full updates.

Files to be created
-------------------
- `update_waveshare/__init__.py` — package exports and simple helpers.
- `update_waveshare/core.py` — main implementation (loading images, diffing, calling IT8951 API).
- `update_waveshare/_device.py` — device factory wrapper for creating `AutoEPDDisplay`/`VirtualEPDDisplay`.
- `update_waveshare/tests/test_core.py` — small unit tests using a virtual display and sample images (in `test/images` or generated programmatically).
- `update_waveshare/README.md` — usage examples.

Quality gates & tests
---------------------
- Unit tests (fast):
  - load a PNG and ensure `display_image` calls device methods (monkeypatch or use virtual display).
  - partial_refresh: given two small images differing in a small rectangle, ensure returned bbox matches expected.
- Integration smoke: run `blank_screen.py`-style script using `VirtualEPDDisplay` to ensure no exceptions.
- Lint/format: follow repo style.

Implementation steps (milestones)
---------------------------------
1. Create package skeleton and the plan (this file) — Completed (this file).
2. Implement device factory and small wrapper that can create a device instance with the same options as `blank_screen.py`.
3. Implement `display_image()` to do a full update (using Pillow + device API).
4. Implement `blank_screen()` calling the device clear method.
5. Implement `partial_refresh()` algorithm and wire into `display_image(mode='auto'|'partial')`.
6. Add unit tests and a small integration script that demonstrates both full and partial updates with `VirtualEPDDisplay`.
7. Run tests and fix issues.

Edge cases and considerations
----------------------------
- Image sizes different from device resolution: images will be centered or scaled; default: scale to fit while preserving aspect ratio, and pad with white/black to device resolution. Provide `fit` and `stretch` options later if desired.
- Large diffs: if the changed area is a large fraction of the screen, prefer full refresh for speed and image quality.
- Color/greyscale conversion: ensure we use the correct pixel depth expected by `IT8951`.
- Device failures: provide clear exceptions and safe fallback (attempt to close device cleanly).
- Multi-process/multi-client: the internal cache approach is per-process; note this in docs.

Next steps
----------
- Review this plan. If you confirm, I will implement step 2 and 3 (package skeleton + device factory + full-display + blanking). After that I'll run unit tests and report back.

Requirements checklist (mapping)
-------------------------------
- Importable package in `update_waveshare/` — Planned
- Accept image files and update display — Planned
- Support partial refreshes — Planned (API + internal cache + diff algorithm)
- Provide blank-screen method — Planned
- Usable via `import` from other Python code — Planned

If anything above needs to change (API names, persistent cache policy, exact partial-update heuristics), tell me now and I will adjust the plan before coding.

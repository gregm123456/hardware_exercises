
# IT8951 — Python e-paper usage guide

This guide explains how to use the `IT8951` Python package in this repository to drive an SPI e-paper display (via the IT8951 controller). It summarizes installation, the main classes and methods, short examples (real and virtual displays), configuration tips (VCOM, SPI speed), and debugging notes.

## Quick checklist

- Install the package (see "Install")
- Enable SPI on your platform and ensure your user has access to the SPI/GPIO groups
- For real hardware use `EPD` or `AutoEPDDisplay`; for development/testing use `VirtualEPDDisplay`
- Use `draw_full()` for whole-screen updates, `draw_partial()` for efficient partial updates

## Contract (tiny)

- Inputs: PIL.Image-compatible image data (frame buffer is a PIL Image in 'L' mode). Many APIs accept raw bytes for pixels.
- Outputs: pixels written to device memory and displayed; Virtual display shows a Tk window.
- Error modes: communication failures raise `RuntimeError`; invalid parameters raise `ValueError`.
- Success: image shows on device (or virtual window); no exception thrown.

## Edge cases to consider

- First update must be a full update (the code falls back to full update if no previous frame exists).
- Partial-update alignment: bounding boxes are aligned to 4 or 8 pixels depending on pixel mode.
- Wrong VCOM may cause poor contrast or artifacts — try different values.
- SPI frequency too high may fail on some hardware — try reducing if communication errors occur.

## Install

From a checkout of the repository, install with pip:

```bash
pip install ./
```

If you need Raspberry Pi GPIO support (optional), install the `rpi` extra:

```bash
pip install .[rpi]
```

Make sure SPI is enabled (for Raspbian use `raspi-config` > Interface Options > SPI) and the current user is in `spi` and `gpio` groups (e.g. `sudo usermod -aG spi,gpio <user>`).

## Key classes and methods (summary)

- `EPD(vcom=-1.5, **spi_kwargs)` — low-level interface to the IT8951 controller
	- `update_system_info()` — reads device size, buffer address, firmware
	- `load_img_area(buf, rotate_mode=..., xy=None, dims=None, pixel_format=...)` — write pixel bytes to controller memory
	- `display_area(xy, dims, display_mode)` — ask controller to refresh that area
	- `set_vcom(vcom)` / `get_vcom()` — set/read device VCOM (voltage)
	- `wait_display_ready()` — blocks until LUT engines finish
	- `run()`, `standby()`, `sleep()` — power/system commands

- `AutoEPDDisplay` — convenience wrapper that ties an `EPD` instance to a PIL frame buffer and provides `draw_full()` and `draw_partial()` methods. It handles packing and sending pixel data via `EPD`.

- `AutoDisplay` — base class that maintains a PIL `frame_buf` (mode 'L'), tracks `prev_frame` and provides `draw_full()`, `draw_partial()` and `clear()` logic.

- `VirtualEPDDisplay` — a test-only UI that shows the display contents in a Tkinter window instead of real hardware.

## Pixel & display modes

- Pixel formats: `PixelModes.M_2BPP`, `M_4BPP`, `M_8BPP` (the library defaults to 4bpp for updates).
- Display modes (waveform): e.g. `DisplayModes.INIT`, `DU`, `GC16`, `GL16` — choose according to desired update behavior. `DU` and other low-bpp modes are faster but limited.
- `low_bpp_modes` (INIT, DU, DU4, A2) use 2bpp packing and change the bounding box rounding.

## Examples

Minimal example using a virtual display (desktop testing):

```python
from IT8951.display import VirtualEPDDisplay
from PIL import Image, ImageDraw

disp = VirtualEPDDisplay(dims=(800,600))
draw = ImageDraw.Draw(disp.frame_buf)
draw.rectangle((10,10,200,100), fill=0)  # draw black box on white background
disp.draw_full(mode=Disp = __import__('IT8951.constants', fromlist=['DisplayModes']).DisplayModes.INIT)

# keep window open (or let the object be alive)
```

Example using the hardware convenience wrapper (`AutoEPDDisplay`):

```python
from IT8951.display import AutoEPDDisplay
from IT8951.constants import DisplayModes
from PIL import Image, ImageDraw

disp = AutoEPDDisplay(vcom=-2.06, bus=0, device=0, spi_hz=24000000)
# draw into the buffer
draw = ImageDraw.Draw(disp.frame_buf)
draw.text((10,10), 'Hello EPD', fill=0)
# full-screen update
disp.draw_full(DisplayModes.INIT)

# later, make a small change and do a partial update
draw.rectangle((10,30,120,80), fill=255)
disp.draw_partial(DisplayModes.DU)
```

Notes: the `AutoEPDDisplay` will create an internal `EPD` with the `spi_hz` you provide; the `EPD` instance exposes lower-level APIs if you need fine control.

## Partial updates

- `AutoDisplay.draw_partial()` compares `prev_frame` to `frame_buf`, computes a bounding box, aligns it to 4 or 8-pixel boundaries, and sends only that region to the device.
- On the first update since initialization `prev_frame` is `None` and a full update will be performed automatically.

## VCOM and performance

- The `vcom` parameter passed to `EPD` or `AutoEPDDisplay` controls VCOM voltage. Try different values (negative floats) to find the best contrast for your panel.
- The SPI clock for pixel transfers is set by `spi_hz` (default 24 MHz in tests). You can increase it experimentally; reduce it if you see communication errors.

## Where to look for examples and tests

- Integration examples are in `test/integration/` (e.g. `test.py`, `time_full.py`, `time_partial.py`). Those show usage patterns and argument examples.

## Troubleshooting

- Communication failure when reading device info: ensure SPI is enabled and pins are correct; check that user is in `spi`/`gpio` groups.
- Strange artifacts or poor contrast: try different `vcom` values.
- If you see value errors for pixel format, ensure you're passing a valid `PixelModes` value.

## Next steps / suggestions

- Use the integration tests as working examples for real devices.
- If you need automated tests for your hardware, add a small CI-friendly harness that can run in virtual mode.

---

This document was generated from the code in the `IT8951` package (notably `display.py`, `interface.py`, and `constants.py`) and the package README.


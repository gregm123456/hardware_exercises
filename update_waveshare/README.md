# update_waveshare

Helpers to update an IT8951 / Waveshare e-paper display from image files.

This small package provides convenience functions to prepare images and send
them to an IT8951-based e-paper display (Waveshare panels commonly use this
controller). It is intentionally lightweight: the image preparation logic lives
here while the low-level device driver is expected to be provided by the
`IT8951` package (either installed into your Python environment or present in
the repository alongside this package).

Contents
 - `core.py` — high-level helpers: `display_image()` and `blank_screen()`.
 - `_device.py` — small device factory that locates and imports the local
	 `IT8951` package if possible, and returns either a real or virtual display
	 object.
 - `simple_update.py` — a tiny command-line utility that shows how to use the
	 API from the command line.

Installation
 - This package needs Pillow (PIL) for image handling. Install dependencies with:

```bash
pip install -r update_waveshare/requirements.txt
```

 - You also need the `IT8951` driver package. Either install it in your
	 environment (pip / system package) or keep the `IT8951` source/build folder
	 next to this package — `_device.py` will try to add the repository-local
	 `IT8951/src` or the built `IT8951/build/...` path to `sys.path` automatically.

Quick example (Python)

```python
from update_waveshare.core import display_image, blank_screen

# Show an image on a virtual display (no hardware)
regions = display_image('/path/to/photo.png', virtual=True)
print('Updated regions:', regions)

# Blank the real display (if connected)
blank_screen()
```

API: core.display_image()
--------------------------------
Signature (summary):

display_image(image_path: str, *, prev_image_path: Optional[str] = None, device=None, vcom: float = -2.06, rotate: Optional[str] = None, mirror: bool = False, virtual: bool = False, mode: str = 'auto', dither: bool = False, two_pass: bool = False, no_quant: bool = False, gamma: float = 1.0) -> Optional[List[Tuple[int,int,int,int]]]

Key behaviour and parameters:
- image_path: Path to the image file to display. Images are opened with
	Pillow and converted to 'L' (grayscale) for the display.
- prev_image_path: Optional path to a previous image. If provided and a
	partial update is reasonable, a single bounding box of changed pixels is
	computed and the library will attempt a partial refresh.
- device: Pass a pre-initialised device object (an `AutoEPDDisplay` or
	`VirtualEPDDisplay` from the `IT8951.display` module). If omitted, a device
	will be created using `_device.create_device()` with the provided vcom /
	rotate / mirror / virtual options.
- vcom / rotate / mirror: Passed through to the device factory when
	creating a device.
- virtual: If True, a `VirtualEPDDisplay` is used. This is useful for
	development and testing without hardware.
- mode: One of 'auto' (default), 'full' or 'partial'.
	- 'full': force a full-screen update. The image will be quantized to
		4bpp (GC16) by default (see `no_quant` to override).
	- 'partial': prefer a partial update if `prev_image_path` is provided and a
		difference bbox is found.
	- 'auto': will perform a partial update when `prev_image_path` is present
		and the device supports it; otherwise a full update is used.
- dither: When True and doing a 4bpp (GC16) full update, use Floyd–Steinberg
	dithering during quantization to preserve detail.
- two_pass: When True and doing a full update, run the GC16 pass followed by
	a second DU pass to improve contrast/edge cleanliness on some panels.
- no_quant: When True and doing a full update, skip quantization and send an
	8-bit image to the device instead of converting to 4bpp. Useful when the
	driver or display expects plain 8-bit grayscale.
- gamma: Gamma correction factor (default 1.0 = no correction). Values > 1.0
	lighten midtones while preserving black and white points, making images
	appear brighter on e-paper displays. Typical values: 1.5-2.2 for brightening.
	This is applied after grayscale conversion but before quantization.

Return value:
- A list of updated regions (one or more (minx, miny, maxx, maxy) tuples) or
	an empty list if no changes were necessary. The list may be None in some
	error/edge cases.

Notes about image preparation
- Images are scaled to fit the display while preserving aspect ratio, then
	centered on a white background matching the display resolution.
- For full updates the library by default quantizes images to 4 bits per
	pixel (16 gray levels, GC16) for best compatibility with the Waveshare/IT8951
	full-update mode. Use `no_quant=True` to send 8-bit grayscale instead.

Partial updates
- When a `prev_image_path` is provided, the library computes the minimal
	bounding box containing differences and aligns it to a small tile size
	(rounded to multiples of 4 pixels) because many controllers require
	region dimensions to be aligned. If no difference is found, no update is
	performed.

Utility: simple_update.py
--------------------------------
`simple_update.py` is a tiny command-line wrapper around `display_image()` and
`blank_screen()` to make quick testing and scripting easy.

Usage (examples):

Run with an image on the virtual display:

```bash
python update_waveshare/simple_update.py /path/to/image.png --virtual
```

Run as a module (recommended when package is installed):

```bash
python -m update_waveshare.simple_update /path/to/image.png --virtual
```

Blank the screen:

```bash
python update_waveshare/simple_update.py --blank
```

Available CLI flags (short summary):
- `--prev` : path to previous image for partial updates
- `--virtual` : use a virtual display rather than hardware
- `--blank` : clear the display instead of showing an image
- `--mode` : one of `auto`, `full`, `partial` (default `auto`)
- `--vcom` : VCOM voltage (float)
- `--rotate` : `CW`, `CCW` or `flip`
- `--mirror` : mirror the display horizontally
- `--dither` : enable dithering for 4bpp quantization
- `--two-pass` : run a GC16 full pass followed by a DU full pass
- `--no-quant` : send 8-bit image on a full update instead of quantizing
- `--gamma` : gamma correction factor (default 1.0, use 1.5-2.2 for brightening)

Notes on running `simple_update.py` directly
- `simple_update.py` contains a small fallback which inserts the repository
	parent directory into `sys.path` so you can run the script directly from
	the repository (`python update_waveshare/simple_update.py ...`). However
	running it as a module (`python -m update_waveshare.simple_update`) is
	preferable when the package is installed or available on `PYTHONPATH`.

Troubleshooting
--------------------------------
- ImportError for `IT8951`: the device factory (`_device._ensure_it8951_in_path`)
	attempts to add `IT8951/src` or the built library path to `sys.path`. If
	that fails you must either install the `IT8951` package into your Python
	environment (pip / setup.py install) or run from a directory layout where
	the `IT8951` package is adjacent to `update_waveshare` (as in the
	repository this README came from).
- Quantization/dither differences: Pillow builds may not expose some
	quantize methods. The code has fallbacks but if you see unexpected results
	try toggling `--dither` or `--no-quant`.
- Virtual display not appearing: `VirtualEPDDisplay` is provided by the
	`IT8951.display` module; ensure the `IT8951` package version you have
	supports it.

Developer notes
--------------------------------
- `blank_screen()` will call `device.clear()` and, if the helper created the
	device, will attempt to put the underlying hardware into standby. The
	standby call is best-effort and errors are ignored to avoid masking the
	primary clear operation.
- `display_image()` intentionally does not call `device.standby()` after
	updating because callers may run multiple sequential updates and manage
	power state themselves.

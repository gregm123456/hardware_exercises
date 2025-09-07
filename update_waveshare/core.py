"""Core helpers to load images and update a Waveshare/IT8951 display.

This module depends on Pillow (PIL) and the IT8951 package in the repo.
"""
from typing import Optional, Tuple, List
from pathlib import Path
from PIL import Image, ImageChops
import os

from ._device import create_device
from IT8951.constants import DisplayModes


def _load_and_prepare(image_path: str, target_size: Tuple[int,int]) -> Image.Image:
    img = Image.open(image_path).convert('L')
    # scale to fit while preserving aspect ratio, paste on white background
    img.thumbnail(target_size, Image.LANCZOS)
    out = Image.new('L', target_size, 0xFF)
    x = (target_size[0] - img.width)//2
    y = (target_size[1] - img.height)//2
    out.paste(img, (x, y))
    return out


def partial_refresh(prev: Image.Image, new: Image.Image, round_to: int = 4) -> Optional[Tuple[int,int,int,int]]:
    """Return a single bbox (min containing differences) rounded to `round_to` or None if no change."""
    box = ImageChops.difference(prev, new).getbbox()
    if box is None:
        return None
    minx, miny, maxx, maxy = box
    minx -= minx % round_to
    miny -= miny % round_to
    maxx += round_to - 1 - (maxx-1) % round_to
    maxy += round_to - 1 - (maxy-1) % round_to
    return (minx, miny, maxx, maxy)


def display_image(image_path: str, *, prev_image_path: Optional[str] = None, device=None, vcom: float = -2.06, rotate: Optional[str] = None, mirror: bool = False, virtual: bool = False, mode: str = 'auto') -> Optional[List[Tuple[int,int,int,int]]]:
    """Display `image_path` on the device.

    If `prev_image_path` is provided and `mode` allows, compute a partial update.
    Returns a list of updated regions (bboxes) or None.
    """
    # create device if needed
    created = False
    if device is None:
        device = create_device(vcom=vcom, rotate=rotate, mirror=mirror, virtual=virtual)
        created = True

    # prepare images
    target_size = (device.width, device.height)
    new_img = _load_and_prepare(image_path, target_size)

    prev_img = None
    if prev_image_path:
        if os.path.exists(prev_image_path):
            prev_img = _load_and_prepare(prev_image_path, target_size)

    # if mode==full or no prev image, do full
    regions = []
    if mode == 'full' or prev_img is None:
        device.frame_buf.paste(new_img)
        # use an 8-bit-per-pixel mode for full-image updates (matches tests)
        device.draw_full(DisplayModes.GC16)
        regions = [(0,0,device.width,device.height)]
    else:
        # compute bbox
        bbox = partial_refresh(prev_img, new_img)
        if bbox is None:
            regions = []
        else:
            # paste only into device.frame_buf then call draw_partial which will compute diffs itself
            device.frame_buf.paste(new_img)
            device.draw_partial(DisplayModes.DU)
            regions = [bbox]

    # Do not call device standby/sleep immediately here — that can interrupt
    # the host-driven refresh sequence. Let the caller manage power state.

    return regions


def blank_screen(device=None, vcom: float = -2.06, rotate: Optional[str] = None, mirror: bool = False, virtual: bool = False):
    """Clear the display (white) using the device clear/AutoDisplay.clear method."""
    created = False
    if device is None:
        device = create_device(vcom=vcom, rotate=rotate, mirror=mirror, virtual=virtual)
        created = True

    device.clear()

    if created:
        try:
            if hasattr(device, 'epd'):
                try:
                    device.epd.standby()
                except Exception:
                    pass
        except Exception:
            pass

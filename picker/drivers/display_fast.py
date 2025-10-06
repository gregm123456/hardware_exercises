"""Simple local display adapter used by picker during development.

This module provides a simulated fast blit/partial-update interface backed by Pillow and
writes bitmaps to /tmp for inspection. On a real Pi this module should be replaced or
extended to use IT8951/Waveshare drivers.
"""
from pathlib import Path
from typing import Tuple

from PIL import Image

OUT_DIR = Path("/tmp/picker_display")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def init():
    """Initialize display adapter. Try to use the project's IT8951/Waveshare helper
    when available (update_waveshare.create_device). Otherwise stay in virtual mode.
    """
    try:
        # Import local helper that locates the IT8951 code inside the repo
        from update_waveshare._device import create_device
        # Create a virtual device if caller wants to override; we'll store it for later
        # For now we don't keep the device object globally; display functions will create as needed.
        return True
    except Exception:
        return True


def blit(full_bitmap: Image.Image, file_label: str = "frame") -> Path:
    """Write a full-screen bitmap to the real display if available; otherwise save to /tmp.

    If the project's update_waveshare helpers exist, use them to display the image with
    the best available path. Otherwise save a PNG to /tmp for inspection.
    """
    # Try to use the update_waveshare helper which wraps IT8951 and fast paths
    try:
        from update_waveshare.core import display_image
        # Save a temporary image to a file and call display_image on it.
        tmp = OUT_DIR / f"{file_label}.png"
        full_bitmap.save(tmp)
        try:
            # Use 'auto' mode which selects a fast path
            display_image(str(tmp), virtual=False, mode='auto')
        except Exception:
            # If display_image fails, fallback to saving file only
            pass
        return tmp
    except Exception:
        p = OUT_DIR / f"{file_label}.png"
        full_bitmap.save(p)
        return p


def partial_update(_rect: Tuple[int, int, int, int]):
    """No-op in simulation; on hardware trigger partial refresh of rect."""
    return True


def full_update():
    """No-op for simulation; on hardware trigger full refresh."""
    return True

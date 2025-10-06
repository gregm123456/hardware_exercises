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
    """Initialize display adapter. On hardware this will open device handles."""
    return True


def blit(full_bitmap: Image.Image, file_label: str = "frame") -> Path:
    """Write a full-screen bitmap to a file for inspection. Returns the path."""
    p = OUT_DIR / f"{file_label}.png"
    full_bitmap.save(p)
    return p


def partial_update(_rect: Tuple[int, int, int, int]):
    """No-op in simulation; on hardware trigger partial refresh of rect."""
    return True


def full_update():
    """No-op for simulation; on hardware trigger full refresh."""
    return True

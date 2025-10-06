"""UI composition utilities for the picker overlay.

Uses Pillow to compose a simple overlay with a title and 12-item list and returns a
PIL Image object. The selected item is inverted.
"""
from typing import List, Tuple
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# default display size for composition (will be overridden by real driver)
DISPLAY_W = 1024
DISPLAY_H = 600

FONT_PATH = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_SIZE = 28


def compose_overlay(title: str, values: List[str], selected_index: int, full_screen: Tuple[int, int] = (DISPLAY_W, DISPLAY_H)) -> Image.Image:
    w, h = full_screen
    img = Image.new("L", (w, h), color=255)  # white background (L mode)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    # Title
    margin = 16
    y = margin
    draw.text((margin, y), title, font=font, fill=0)
    y += FONT_SIZE + 8

    # Layout 12 items vertically spaced
    item_h = (h - y - margin) // 12
    for i in range(12):
        text = values[i] if i < len(values) else ""
        box_y0 = y + i * item_h
        box_y1 = box_y0 + item_h
        # selected -> draw black rectangle and white text
        if i == selected_index:
            draw.rectangle((0, box_y0, w, box_y1), fill=0)
            draw.text((margin, box_y0 + (item_h - FONT_SIZE) // 2), text, font=font, fill=255)
        else:
            draw.text((margin, box_y0 + (item_h - FONT_SIZE) // 2), text, font=font, fill=0)

    return img


if __name__ == "__main__":
    # quick visual smoke test
    title = "Sample Category"
    vals = [f"Item {i+1}" for i in range(12)]
    img = compose_overlay(title, vals, 3, full_screen=(800, 600))
    img.save("/tmp/picker_overlay.png")
    print("Wrote /tmp/picker_overlay.png")

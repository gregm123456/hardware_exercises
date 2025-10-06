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

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

# Base font size is calculated relative to the display height if not overridden
# Increased so text is much larger on the physical display
DEFAULT_BASE_FONT_RATIO = 0.06  # ~6% of shorter display dimension


def _choose_font_path():
    for p in FONT_PATHS:
        try:
            if Path(p).exists():
                return p
        except Exception:
            continue
    return None


def compose_overlay(title: str, values: List[str], selected_index: int, full_screen: Tuple[int, int] = (DISPLAY_W, DISPLAY_H)) -> Image.Image:
    w, h = full_screen
    img = Image.new("L", (w, h), color=255)  # white background (L mode)
    draw = ImageDraw.Draw(img)

    # Compute font sizes relative to display
    short_dim = min(w, h)
    base_font_size = max(12, int(short_dim * DEFAULT_BASE_FONT_RATIO))
    title_font_size = int(base_font_size * 1.2)
    item_font_size = base_font_size

    font_path = _choose_font_path()
    try:
        if font_path:
            title_font = ImageFont.truetype(font_path, title_font_size)
            item_font = ImageFont.truetype(font_path, item_font_size)
        else:
            raise Exception("no font path")
    except Exception:
        title_font = ImageFont.load_default()
        item_font = ImageFont.load_default()

    # Title
    margin = int(base_font_size * 0.6)
    y = margin
    draw.text((margin, y), title, font=title_font, fill=0)
    # Advance by title height
    try:
        title_h = title_font.getsize(title)[1]
    except Exception:
        title_h = title_font_size
    y += title_h + int(base_font_size * 0.4)

    # Layout 12 items vertically spaced
    item_h = max(18, (h - y - margin) // 12)
    side_pad = int(margin * 0.6)
    for i in range(12):
        text = values[i] if i < len(values) else ""
        box_y0 = y + i * item_h
        box_y1 = box_y0 + item_h
        text_y = box_y0 + max(0, (item_h - item_font_size) // 2)
        # selected -> draw black rectangle inset by side_pad and white text
        if i == selected_index:
            draw.rectangle((side_pad, box_y0, w - side_pad, box_y1), fill=0)
            draw.text((margin, text_y), text, font=item_font, fill=255)
        else:
            draw.text((margin, text_y), text, font=item_font, fill=0)

    return img


def compose_message(message: str, full_screen: Tuple[int, int] = (DISPLAY_W, DISPLAY_H)) -> Image.Image:
    """Compose a large centered message (used for GO / RESET screens).

    Returns an L-mode PIL Image sized to full_screen.
    """
    w, h = full_screen
    img = Image.new("L", (w, h), color=255)
    draw = ImageDraw.Draw(img)

    # Large message font scaled to display
    short_dim = min(w, h)
    msg_font_size = max(24, int(short_dim * 0.12))
    font_path = _choose_font_path()
    try:
        if font_path:
            font = ImageFont.truetype(font_path, msg_font_size)
        else:
            raise Exception("no font path")
    except Exception:
        font = ImageFont.load_default()

    # center text
    # Compute text width/height in a way compatible with multiple Pillow versions
    if hasattr(draw, 'textbbox'):
        bbox = draw.textbbox((0, 0), message, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    elif hasattr(draw, 'textsize'):
        tw, th = draw.textsize(message, font=font)
    else:
        try:
            tw, th = font.getsize(message)
        except Exception:
            # fallback approximate
            tw = len(message) * (msg_font_size * 2)
            th = msg_font_size
    x = (w - tw) // 2
    y = (h - th) // 2
    draw.text((x, y), message, font=font, fill=0)
    return img


if __name__ == "__main__":
    # quick visual smoke test
    title = "Sample Category"
    vals = [f"Item {i+1}" for i in range(12)]
    img = compose_overlay(title, vals, 3, full_screen=(800, 600))
    img.save("/tmp/picker_overlay.png")
    print("Wrote /tmp/picker_overlay.png")

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


def compose_main_screen(texts: dict, positions: dict, full_screen: Tuple[int, int] = (DISPLAY_W, DISPLAY_H), placeholder_path: str = None, rotate_output: str = None) -> Image.Image:
    """Compose the main idle screen.

    Layout: top-centred placeholder image (reserved 512x512 area where possible),
    below which the currently selected values for knobs are listed.

    - `texts` is the loaded texts mapping (e.g. load_texts()).
    - `positions` is a dict mapping channel int -> position int (0..11).
    - `placeholder_path` optionally overrides the default asset location.
    Returns an L-mode PIL Image sized to full_screen.
    """
    w, h = full_screen

    # If full_screen is landscape but we want the logical layout to be
    # portrait (narrow/tall), compose on a portrait canvas (h x w) and then
    # rotate the final image back to landscape. This produces a landscape
    # PNG whose internal contents are portrait — matching a display mounted
    # rotated 90 degrees.
    auto_rotated = False
    if w > h:
        layout_w, layout_h = h, w
        auto_rotated = True
    else:
        layout_w, layout_h = w, h

    img = Image.new("L", (layout_w, layout_h), color=255)
    draw = ImageDraw.Draw(img)

    # Determine desired reserved image size from texts meta or default
    max_img_size = 512
    try:
        meta = texts.get('meta', {}) if isinstance(texts, dict) else {}
        reserved = meta.get('reserved_image_area', {})
        desired_w = int(reserved.get('width', max_img_size))
        desired_h = int(reserved.get('height', max_img_size))
    except Exception:
        desired_w = max_img_size
        desired_h = max_img_size

    # Clamp desired to available layout. Prefer to show the placeholder at the
    # desired size if there's room; otherwise scale down to fit.
    pad = 20
    avail_w = max(0, layout_w - pad)
    avail_h = max(0, layout_h - pad)
    if avail_w >= desired_w and avail_h >= desired_h + 100:
        # Enough space to show desired size and leave room for text
        img_w = min(desired_w, avail_w)
        img_h = min(desired_h, avail_h)
    else:
        # Fallback: use a fraction of layout height (previous behaviour)
        img_w = min(max_img_size, layout_w - 20)
        img_h = min(max_img_size, max(64, layout_h // 3))

    # locate placeholder asset if not provided
    if not placeholder_path:
        try:
            candidate = Path(__file__).parent / 'assets' / 'placeholder.png'
            if candidate.exists():
                placeholder_path = str(candidate)
        except Exception:
            placeholder_path = None

    # load or synthesize placeholder
    placeholder_img = None
    if placeholder_path:
        try:
            placeholder_img = Image.open(placeholder_path).convert('L')
        except Exception:
            placeholder_img = None

    if placeholder_img is None:
        # synthesize a simple placeholder graphic
        placeholder_img = Image.new('L', (img_w, img_h), 0xEE)
        pd = ImageDraw.Draw(placeholder_img)
        try:
            fpath = _choose_font_path()
            font = ImageFont.truetype(fpath, 24) if fpath else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        text = "PLACEHOLDER"
        if hasattr(pd, 'textbbox'):
            bb = pd.textbbox((0, 0), text, font=font)
            tw = bb[2] - bb[0]
            th = bb[3] - bb[1]
        else:
            tw, th = pd.textsize(text, font=font)
        pd.text(((img_w - tw) // 2, (img_h - th) // 2), text, font=font, fill=0)

    # Resize placeholder to exactly fit the reserved area 
    try:
        placeholder_img = placeholder_img.resize((img_w, img_h), Image.LANCZOS)
    except Exception:
        pass
    
    px = (layout_w - placeholder_img.width) // 2
    py = 8
    img.paste(placeholder_img, (px, py))

    # Draw selected knob values below the image
    short_dim = min(w, h)
    base_font_size = max(12, int(short_dim * DEFAULT_BASE_FONT_RATIO))
    font_path = _choose_font_path()
    try:
        if font_path:
            item_font = ImageFont.truetype(font_path, base_font_size)
        else:
            raise Exception("no font")
    except Exception:
        item_font = ImageFont.load_default()

    # Collect selected non-empty values in physical knob order (top->bottom)
    # Physical layout mapping (requested):
    #  - upper right: CH4
    #  - top left:   CH0
    #  - mid right:  CH5
    #  - mid left:   CH1
    #  - bottom right: CH6
    #  - bottom left:  CH2
    knob_order = [4, 0, 5, 1, 6, 2]
    entries = []
    for ch in knob_order:
        key = f"CH{ch}"
        knob = texts.get(key)
        values = knob.get('values', [""] * 12) if knob else [""] * 12
        pos = positions.get(ch, 0)
        sel = values[pos] if pos < len(values) else ""
        if sel and sel.strip():
            entries.append((knob.get('title', key) if knob else key, sel))

    # Layout entries in a simple vertical list
    margin = 8
    y = py + placeholder_img.height + margin
    side_x = 12
    for title, sel in entries:
        # draw title: value
        try:
            draw.text((side_x, y), f"{title}: {sel}", font=item_font, fill=0)
            if hasattr(item_font, 'getsize'):
                line_h = item_font.getsize(title)[1]
            else:
                line_h = base_font_size
        except Exception:
            draw.text((side_x, y), f"{title}: {sel}", fill=0)
            line_h = base_font_size
        y += max(line_h + 4, base_font_size + 4)

    # Apply requested output rotation (convenience for saving a portrait-oriented
    # image when the display is mounted rotated). This does not change how
    # `PickerCore` composes images (it uses `effective_display_size`) and `blit`
    # may also apply rotation when sending to the physical display.
    if rotate_output:
        try:
            if rotate_output == 'CW':
                img = img.rotate(-90, expand=True)
            elif rotate_output == 'CCW':
                img = img.rotate(90, expand=True)
            elif rotate_output == 'flip':
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
        except Exception:
            # ignore rotation errors and return original
            pass

    # If we composed on a portrait canvas but the requested full_screen was
    # landscape, rotate the result so the returned image has the original
    # full_screen dimensions (landscape) but portrait-oriented contents.
    if auto_rotated:
        try:
            img = img.rotate(-90, expand=True)
        except Exception:
            pass

    # Apply any explicit requested rotation on top of auto-rotation
    if rotate_output:
        try:
            if rotate_output == 'CW':
                img = img.rotate(-90, expand=True)
            elif rotate_output == 'CCW':
                img = img.rotate(90, expand=True)
            elif rotate_output == 'flip':
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
        except Exception:
            pass

    return img


if __name__ == "__main__":
    # quick visual smoke test
    title = "Sample Category"
    vals = [f"Item {i+1}" for i in range(12)]
    img = compose_overlay(title, vals, 3, full_screen=(800, 600))
    img.save("/tmp/picker_overlay.png")
    print("Wrote /tmp/picker_overlay.png")

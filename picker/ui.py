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
    # Reduce base font size slightly to allow two-line entries in tight spaces
    base_font_size = max(10, int(short_dim * (DEFAULT_BASE_FONT_RATIO * 0.9)))
    font_path = _choose_font_path()
    try:
        if font_path:
            # Try to load a bold and a regular variant from same path (many
            # systems provide a bold file in FONT_PATHS list). If the same path
            # is a bold face, use it for titles and load a default for values.
            title_font = ImageFont.truetype(font_path, base_font_size)
            # Attempt to load a non-bold variant by replacing 'Bold' in the
            # filename; fall back to the same font if not available.
            try:
                regular_path = font_path.replace('Bold', '')
                value_font = ImageFont.truetype(regular_path, base_font_size)
            except Exception:
                value_font = ImageFont.truetype(font_path, base_font_size)
        else:
            raise Exception("no font")
    except Exception:
        title_font = ImageFont.load_default()
        value_font = ImageFont.load_default()

    # Fixed six entries in the interleaved physical knob order (top->bottom).
    # Triplets: right-side knobs are CH0,CH1,CH2 (even indices in the list)
    # and left-side knobs are CH4,CH5,CH6 (odd indices in the list).
    # Order top-to-bottom: [0 (right), 4 (left), 1 (right), 5 (left), 2 (right), 6 (left)]
    knob_order = [0, 4, 1, 5, 2, 6]
    entries = []
    for ch in knob_order:
        key = f"CH{ch}"
        knob = texts.get(key)
        values = knob.get('values', [""] * 12) if knob else [""] * 12
        pos = positions.get(ch, 0)
        sel = values[pos] if pos < len(values) else ""
        title = knob.get('title', key) if knob else key
        entries.append((title, sel))

    # Space the six entries evenly in the vertical area below the placeholder
    # image, spanning from just below the image down to the bottom padding.
    n = len(entries)
    margin = 8
    area_y0 = py + placeholder_img.height + margin
    area_y1 = layout_h - pad
    if area_y1 <= area_y0:
        # fallback simple stacking (title on one line, value below)
        side_x = 12
        y = area_y0
        for title, sel in entries:
            try:
                # title bold (or heavy), value regular on next line
                draw.text((side_x, y), title, font=title_font, fill=0)
                if hasattr(title_font, 'getsize'):
                    title_h = title_font.getsize(title)[1]
                else:
                    title_h = base_font_size
                draw.text((side_x, y + title_h + 2), sel, font=value_font, fill=0)
                if hasattr(value_font, 'getsize'):
                    val_h = value_font.getsize(sel)[1]
                else:
                    val_h = base_font_size
            except Exception:
                draw.text((side_x, y), title, fill=0)
                draw.text((side_x, y + base_font_size + 2), sel, fill=0)
                title_h = base_font_size
                val_h = base_font_size
            y += max(title_h + val_h + 6, base_font_size * 2 + 6)
    else:
        area_h = area_y1 - area_y0
        # If we want endpoints included, divide by (n-1) so first is at area_y0 and
        # last is at area_y1
        step = area_h / max(1, (n - 1))
        left_x = 12
        # Add a slightly larger right padding and an extra safety offset to
        # avoid clipping the last glyph when right-justifying text. Some
        # font metrics differ slightly between environments so a small
        # conservative offset helps prevent truncation.
        right_x_pad = 18
        extra_safety = 6
        for i, (title, sel) in enumerate(entries):
            # compute baseline y for this entry and adjust to draw the title
            # stacked above the value. We compute combined height and center the
            # pair on the target baseline.
            try:
                if hasattr(draw, 'textbbox'):
                    tb = draw.textbbox((0, 0), title, font=title_font)
                    title_w = tb[2] - tb[0]
                    title_h = tb[3] - tb[1]
                    vb = draw.textbbox((0, 0), sel, font=value_font)
                    val_w = vb[2] - vb[0]
                    val_h = vb[3] - vb[1]
                else:
                    title_w, title_h = title_font.getsize(title)
                    val_w, val_h = value_font.getsize(sel)
            except Exception:
                title_w = len(title) * (base_font_size // 2)
                title_h = base_font_size
                val_w = len(sel) * (base_font_size // 2)
                val_h = base_font_size

            pair_h = title_h + 2 + val_h
            target_y = int(round(area_y0 + i * step))
            top_y = target_y - pair_h // 2

            # Even indices in knob_order are right-side entries -> right-justify
            # compute max width between title and value to right-justify
            max_w = max(title_w, val_w)
            if i % 2 == 0:
                x = max(left_x, layout_w - right_x_pad - max_w - extra_safety)
            else:
                x = left_x

            # Clip y to visible area
            if top_y < area_y0:
                top_y = area_y0
            if top_y + pair_h > area_y1:
                top_y = area_y1 - pair_h

            try:
                draw.text((x, top_y), title, font=title_font, fill=0)
                draw.text((x, top_y + title_h + 2), sel, font=value_font, fill=0)
            except Exception:
                draw.text((x, top_y), title, fill=0)
                draw.text((x, top_y + title_h + 2), sel, fill=0)

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

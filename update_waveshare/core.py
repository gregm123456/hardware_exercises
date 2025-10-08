"""Core helpers to load images and update a Waveshare/IT8951 display.

This module depends on Pillow (PIL) and the IT8951 package in the repo.
"""
from typing import Optional, Tuple, List
from pathlib import Path
from PIL import Image, ImageChops
import os
import numpy as np

from ._device import create_device
from IT8951.constants import DisplayModes


def _apply_gamma_correction(img: Image.Image, gamma: float) -> Image.Image:
    """Apply gamma correction to a grayscale image.
    
    Gamma correction adjusts the midtones while preserving black and white points.
    gamma > 1.0 lightens midtones (makes image brighter)
    gamma < 1.0 darkens midtones
    gamma = 1.0 no change
    
    Args:
        img: PIL Image in mode 'L' (grayscale)
        gamma: Gamma correction factor (typically 1.0 to 2.5 for brightening)
    
    Returns:
        Gamma-corrected PIL Image
    """
    if gamma == 1.0:
        return img
    
    # Convert to numpy array for efficient gamma correction
    img_array = np.array(img, dtype=np.float32)
    
    # Normalize to 0-1 range
    img_array = img_array / 255.0
    
    # Apply gamma correction: output = input^(1/gamma)
    img_array = np.power(img_array, 1.0 / gamma)
    
    # Scale back to 0-255
    img_array = img_array * 255.0
    
    # Convert back to uint8 and create PIL Image
    img_array = np.clip(img_array, 0, 255).astype(np.uint8)
    
    return Image.fromarray(img_array)


def _load_and_prepare(image_path: str, target_size: Tuple[int,int], target_bpp: Optional[int] = None, dither: bool = False, supersample: int = 1, preview_out: Optional[str] = None, color_mode: str = 'standard', gamma: float = 1.0) -> Image.Image:
    """Load image, resize to target_size and optionally quantize to target_bpp (2/4/8).

    If dither is True and target_bpp is 4, a 16-color Floyd-Steinberg quantize will be used
    to preserve detail when converting to 16 gray levels (GC16).
    
    color_mode options:
    - 'standard': Standard PIL RGB to grayscale conversion
    - 'luminance': Weighted luminance conversion (0.299*R + 0.587*G + 0.114*B)
    - 'average': Simple average of RGB channels
    - 'red', 'green', 'blue': Use single color channel
    
    gamma: Gamma correction factor (1.0 = no change, >1.0 = brighten midtones)
    """
    img = Image.open(image_path)
    
    # Handle color to grayscale conversion based on mode
    if img.mode in ('RGB', 'RGBA'):
        if color_mode == 'luminance':
            # Use standard luminance weights for better perceptual conversion
            img = img.convert('L')
        elif color_mode == 'average':
            # Simple average of RGB channels
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            r, g, b = img.split()
            img = Image.eval(Image.eval(r, lambda x: x//3), lambda x: x + Image.eval(g, lambda y: y//3).load()[0])
            # Simpler approach using numpy-like operations via PIL
            img = img.convert('L')  # Fall back to standard for now - can enhance later
        elif color_mode in ('red', 'green', 'blue'):
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            channels = img.split()
            channel_map = {'red': 0, 'green': 1, 'blue': 2}
            img = channels[channel_map[color_mode]]
        else:  # 'standard' or any other value
            img = img.convert('L')
    elif img.mode == 'L':
        # Already grayscale
        pass
    else:
        # Other modes (P, etc.) - convert to L
        img = img.convert('L')
    # optionally supersample: we render to a larger working canvas then downsample
    if supersample and supersample > 1:
        work_size = (target_size[0]*supersample, target_size[1]*supersample)
    else:
        work_size = target_size

    # scale to fit while preserving aspect ratio, paste on white background
    img.thumbnail(work_size, Image.LANCZOS)
    out = Image.new('L', work_size, 0xFF)
    x = (work_size[0] - img.width)//2
    y = (work_size[1] - img.height)//2
    out.paste(img, (x, y))
    
    # Apply gamma correction if requested (after resize, before quantization)
    if gamma != 1.0:
        out = _apply_gamma_correction(out, gamma)

    if target_bpp is None:
        result = out if supersample and supersample > 1 else out
        # if supersampled, downsample to the target size for return
        if supersample and supersample > 1:
            result = out.resize(target_size, Image.LANCZOS)
        if preview_out:
            try:
                result.save(preview_out)
            except Exception:
                pass
        return result

    # quantize to requested bit depth
    if target_bpp == 8:
        result = out
        if supersample and supersample > 1:
            result = out.resize(target_size, Image.LANCZOS)
        if preview_out:
            try:
                result.save(preview_out)
            except Exception:
                pass
        return result

    if target_bpp == 4:
        # if we supersampled, downsample first to the device size, then quantize
        prep = out
        if supersample and supersample > 1:
            prep = out.resize(target_size, Image.LANCZOS)

        # reduce to 16 gray levels. Use Pillow quantize with dithering if requested.
        if dither:
            try:
                q = prep.quantize(colors=16, method=Image.FLOYDSTEINBERG)
            except Exception:
                # Pillow may have been built without this method; fall back
                q = prep.quantize(colors=16)
        else:
            q = prep.quantize(colors=16)

        res = q.convert('L')
        if preview_out:
            try:
                res.save(preview_out)
            except Exception:
                pass
        return res

    if target_bpp == 2:
        # reduce to 4 gray levels
        prep = out
        if supersample and supersample > 1:
            prep = out.resize(target_size, Image.LANCZOS)
        q = prep.quantize(colors=4)
        res = q.convert('L')
        if preview_out:
            try:
                res.save(preview_out)
            except Exception:
                pass
        return res

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


def display_image(image_path: str, *, prev_image_path: Optional[str] = None, device=None, vcom: float = -2.06, rotate: Optional[str] = None, mirror: bool = False, virtual: bool = False, mode: str = 'auto', dither: bool = False, two_pass: bool = False, no_quant: bool = False, color_mode: str = 'standard', gamma: float = 1.0) -> Optional[List[Tuple[int,int,int,int]]]:
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
    # For 'auto' mode, use the best quality 4BPP dithered path
    # For 'full' mode, choose quantization based on no_quant flag
    if mode == 'auto':
        # Force high-quality 4BPP dithered preparation for auto mode
        new_img = _load_and_prepare(image_path, target_size, target_bpp=4, dither=True, color_mode=color_mode, gamma=gamma)
    elif mode == 'full_quality':
        # For guaranteed best fidelity, prepare full-resolution without quantization
        new_img = _load_and_prepare(image_path, target_size, target_bpp=8, dither=False, color_mode=color_mode, gamma=gamma)
    elif mode == 'full':
        if no_quant:
            new_img = _load_and_prepare(image_path, target_size, target_bpp=8, dither=False, color_mode=color_mode, gamma=gamma)
        else:
            new_img = _load_and_prepare(image_path, target_size, target_bpp=4, dither=dither, color_mode=color_mode, gamma=gamma)
    else:
        new_img = _load_and_prepare(image_path, target_size, color_mode=color_mode, gamma=gamma)

    prev_img = None
    if prev_image_path:
        if os.path.exists(prev_image_path):
            prev_img = _load_and_prepare(prev_image_path, target_size, target_bpp=4, dither=dither if mode=='full' else False, color_mode=color_mode, gamma=gamma)

    # if mode==full or no prev image, do full
    regions = []
    if mode == 'full' or prev_img is None:
        device.frame_buf.paste(new_img)
        
        # For smooth, flicker-free menu updates, use only DU mode for auto
        # But for main screen with images, we need proper grayscale rendering
        if mode == 'auto':
            print("--> Using auto mode: GC16 for image quality")
            device.draw_full(DisplayModes.GC16)
        elif mode == 'FAST':
            print("--> Using FAST mode: DU-only for lightning speed")
            device.draw_full(DisplayModes.DU)
        elif (mode == 'full' and no_quant):
            print("--> Using explicit 8BPP update path")
            from IT8951.constants import PixelModes
            frame = device._get_frame_buf()
            # Check if device supports pixel_format parameter (virtual display doesn't)
            if hasattr(device, 'epd'):
                device.update(frame.tobytes(), (0,0), device.display_dims, DisplayModes.GC16, pixel_format=PixelModes.M_8BPP)
                if two_pass:
                    device.update(frame.tobytes(), (0,0), device.display_dims, DisplayModes.DU, pixel_format=PixelModes.M_8BPP)
            else:
                # Virtual display - just use standard update
                device.update(frame.tobytes(), (0,0), device.display_dims, DisplayModes.GC16)
                if two_pass:
                    device.update(frame.tobytes(), (0,0), device.display_dims, DisplayModes.DU)
            device.prev_frame = frame
        else:
            # Use GC16 for image quality in 4BPP path
            print("--> Using GC16 for image quality (4BPP path)")
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

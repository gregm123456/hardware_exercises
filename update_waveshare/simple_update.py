#!/usr/bin/env python3
"""Simple CLI to update the Waveshare display with a local image file.

Usage: python simple_update.py /path/to/image.png [--virtual]
"""
import argparse
try:
    from .core import display_image, blank_screen
    from ._device import create_device
except Exception:
    # allow running this file as a script (``python update_waveshare/simple_update.py``)
    # by falling back to the package absolute import
    # ensure parent dir is on sys.path so package can be imported when running
    # the file directly.
    import sys
    from pathlib import Path
    parent = str(Path(__file__).resolve().parent.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    from update_waveshare.core import display_image, blank_screen
    from update_waveshare._device import create_device


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('image', nargs='?', help='Path to image file to display')
    p.add_argument('--prev', help='Path to previous image (for partial updates)')
    p.add_argument('--virtual', action='store_true', help='Use virtual display')
    p.add_argument('--blank', action='store_true', help='Blank the screen instead of showing an image')
    p.add_argument('--mode', choices=['auto', 'full', 'partial'], default='auto', help='Update mode')
    p.add_argument('--vcom', type=float, default=-3.00, help='VCOM voltage to use')
    p.add_argument('--rotate', choices=['CW','CCW','flip'], default=None, help='Rotate display')
    p.add_argument('--mirror', action='store_true', help='Mirror display')
    p.add_argument('--dither', action='store_true', help='Enable dithering for full updates')
    p.add_argument('--two-pass', action='store_true', help='Run a GC16 full pass followed by a DU full pass')
    p.add_argument('--no-quant', action='store_true', help='Do not quantize to 4bpp for full updates; send 8bpp instead')
    p.add_argument('--color-mode', choices=['standard', 'luminance', 'average', 'red', 'green', 'blue'], default='standard', help='Color to grayscale conversion method')
    return p.parse_args()


def main():
    args = parse_args()
    if args.blank:
        # If using a virtual device, create and pass the device so we can keep
        # the Tk window open for inspection after clearing the screen.
        if args.virtual:
            dev = create_device(virtual=True)
            blank_screen(device=dev)
            print('Screen blanked (virtual)')
            try:
                input('Press ENTER to close the virtual display...')
            except Exception:
                pass
            # Explicitly destroy the Tk root if present
            if hasattr(dev, 'root'):
                try:
                    dev.root.destroy()
                except Exception:
                    pass
            return

        blank_screen(virtual=args.virtual)
        print('Screen blanked')
        return

    if not args.image:
        print('No image provided. Use --blank or provide an image path.')
        return

    # If virtual, create the device explicitly so we can keep the window open
    # for inspection after the update.
    if args.virtual:
        dev = create_device(virtual=True)
        regions = display_image(args.image, prev_image_path=args.prev, device=dev, virtual=True, mode=args.mode, vcom=args.vcom, rotate=args.rotate, mirror=args.mirror, dither=args.dither, two_pass=args.two_pass, no_quant=args.no_quant, color_mode=args.color_mode)
        print('Updated regions:', regions)
        try:
            input('Press ENTER to close the virtual display...')
        except Exception:
            pass
        if hasattr(dev, 'root'):
            try:
                dev.root.destroy()
            except Exception:
                pass
    else:
        regions = display_image(args.image, prev_image_path=args.prev, virtual=args.virtual, mode=args.mode, vcom=args.vcom, rotate=args.rotate, mirror=args.mirror, dither=args.dither, two_pass=args.two_pass, no_quant=args.no_quant, color_mode=args.color_mode)
        print('Updated regions:', regions)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Simple CLI to update the Waveshare display with a local image file.

Usage: python simple_update.py /path/to/image.png [--virtual]
"""
import argparse
try:
    from .core import display_image, blank_screen
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


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('image', nargs='?', help='Path to image file to display')
    p.add_argument('--prev', help='Path to previous image (for partial updates)')
    p.add_argument('--virtual', action='store_true', help='Use virtual display')
    p.add_argument('--blank', action='store_true', help='Blank the screen instead of showing an image')
    return p.parse_args()


def main():
    args = parse_args()
    if args.blank:
        blank_screen(virtual=args.virtual)
        print('Screen blanked')
        return

    if not args.image:
        print('No image provided. Use --blank or provide an image path.')
        return

    regions = display_image(args.image, prev_image_path=args.prev, virtual=args.virtual, mode='auto')
    print('Updated regions:', regions)


if __name__ == '__main__':
    main()

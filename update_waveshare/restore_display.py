#!/usr/bin/env python3
"""Small helper to force a GC16 + DU full refresh to restore controller waveform state.

Usage: python -m update_waveshare.restore_display [--virtual] [--vcom VCOM]
"""
import argparse
from ._device import create_device
from IT8951.constants import DisplayModes
from time import sleep


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--virtual', action='store_true', help='Use virtual display')
    p.add_argument('--vcom', type=float, default=-2.06, help='VCOM voltage to use')
    return p.parse_args()


def main():
    args = parse_args()
    dev = create_device(vcom=args.vcom, virtual=args.virtual)

    # ensure controller is running/woken from standby
    try:
        if hasattr(dev, 'epd'):
            dev.epd.run()
            # small delay to let controller settle
            sleep(0.2)
    except Exception:
        pass

    # paste current frame buffer (already white or whatever) and run GC16 then DU
    # try multiple GC16 passes with short delays to ensure LUTs are applied
    print('Running GC16 full pass (x2)...')
    dev.draw_full(DisplayModes.GC16)
    sleep(0.2)
    dev.draw_full(DisplayModes.GC16)
    sleep(0.2)
    print('Running DU second pass...')
    dev.draw_full(DisplayModes.DU)

    # do not force standby here; caller can choose to power-manage afterwards
    print('Done: waveform restore complete')


if __name__ == '__main__':
    main()

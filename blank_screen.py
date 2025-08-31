#!/usr/bin/env python3
"""Clear the IT8951 e-paper display.

This script mirrors the project's integration test style: by default it will
use the real device (AutoEPDDisplay). Use --virtual to run a local Tk window
for testing without hardware.
"""

from time import sleep
import argparse


def parse_args():
	p = argparse.ArgumentParser(description='Clear the EPD (real or virtual)')
	p.add_argument('-v', '--virtual', action='store_true',
				   help='use a Tkinter window instead of the physical device')
	p.add_argument('-r', '--rotate', default=None, choices=['CW', 'CCW', 'flip'],
				   help='rotate display')
	p.add_argument('-m', '--mirror', action='store_true',
				   help='mirror the display')
	p.add_argument('--vcom', type=float, default=-2.06,
				   help='VCOM voltage for the device (only for real device)')
	return p.parse_args()


def main():
	args = parse_args()

	if not args.virtual:
		from IT8951.display import AutoEPDDisplay

		print('Initializing EPD...')
		display = AutoEPDDisplay(vcom=args.vcom, rotate=args.rotate, mirror=args.mirror)
		try:
			print('Clearing display...')
			display.clear()
			# give the device a moment to finish any work
			sleep(0.5)
		finally:
			# device-specific cleanup (if any) can be added here later
			pass

	else:
		from IT8951.display import VirtualEPDDisplay
		display = VirtualEPDDisplay(dims=(800, 600), rotate=args.rotate, mirror=args.mirror)
		print('Clearing virtual display...')
		display.clear()
		# keep the virtual window open briefly so the user can see the result
		sleep(1.0)

	print('Done.')


if __name__ == '__main__':
	main()


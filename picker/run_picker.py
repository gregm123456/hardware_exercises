"""CLI runner for the picker app.

Provides --simulate and --config options. In simulate mode, uses SimulatedMCP3008.
"""
import argparse
import signal
import sys

from picker.hw import HW, SimulatedMCP3008, Calibration
from picker.config import load_texts, DEFAULT_DISPLAY
from picker.core import PickerCore


def main(argv=None):
    p = argparse.ArgumentParser(description="Run the picker application")
    p.add_argument("--simulate", action="store_true", help="Run with simulated ADC values")
    p.add_argument("--config", help="Path to texts JSON config (defaults to picker/sample_texts.json)")
    p.add_argument("--display-w", type=int, default=1024)
    p.add_argument("--display-h", type=int, default=600)
    args = p.parse_args(argv)

    texts = load_texts(args.config) if args.config else load_texts()

    if args.simulate:
        adc = SimulatedMCP3008()
    else:
        adc = None  # real ADC reader to be implemented / wired here

    calib_map = {ch: Calibration() for ch in range(8)}
    hw = HW(adc_reader=adc, calib_map=calib_map)

    core = PickerCore(hw, texts, display_size=(args.display_w, args.display_h))

    def handle_sigint(sig, frame):
        print('Stopping...')
        core.running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    core.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Interactive MCP3008 calibrator.

- Continuously samples all 8 channels until you press Enter.
- Detects "settled" values per channel (stable over a short window) and clusters them as positions.
- Updates an in-place terminal display while running.
- When Enter is pressed, writes a JSON calibration file and prints a table report.

Calibration file format (JSON):
{
  "vref": 3.3,
  "adc_vref": 3.3,
  "channels": {
    "0": [0.000, 0.123, ...],
    "1": [ ... ]
  }
}

This is intentionally conservative about floating transients: a windowed range threshold is used
for stability detection before registering a value.
"""

import Adafruit_MCP3008
import Adafruit_GPIO.SPI as SPI
import time
import threading
import collections
import json
import argparse
import sys
import math

SPI_PORT = 0
SPI_DEVICE = 1  # CE1


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


class ChannelCalibrator:
    def __init__(self, ch_index, vref, adc_vref, window_size, settle_thresh, cluster_tol):
        self.ch = ch_index
        self.vref = vref
        self.adc_vref = adc_vref
        self.window = collections.deque(maxlen=window_size)
        self.settle_thresh = settle_thresh
        self.cluster_tol = cluster_tol
        # detected positions: list of (value, count) for incremental average
        self.positions = []
        self.last_reported = None

    def push_adc(self, adc_val):
        v = (adc_val / 1023.0) * (self.adc_vref if self.adc_vref is not None else self.vref)
        self.window.append(v)

    def window_stats(self):
        if not self.window:
            return None, None
        mn = min(self.window)
        mx = max(self.window)
        med = median(list(self.window))
        return med, (mx - mn)

    def maybe_register(self):
        med, r = self.window_stats()
        if med is None:
            return None
        # settled if range within threshold
        if r <= self.settle_thresh:
            # cluster with existing positions
            for i, (pv, cnt) in enumerate(self.positions):
                if abs(pv - med) <= self.cluster_tol:
                    # update running average
                    new_cnt = cnt + 1
                    new_pv = (pv * cnt + med) / new_cnt
                    self.positions[i] = (new_pv, new_cnt)
                    self.last_reported = new_pv
                    return new_pv
            # new position
            self.positions.append((med, 1))
            self.last_reported = med
            return med
        else:
            # not settled
            self.last_reported = None
            return None

    def get_positions_values(self):
        return [pv for (pv, cnt) in self.positions]


def human_table(channels_values, precision=3):
    # channels_values: dict ch -> list of values
    lines = []
    header = "CH | positions"
    lines.append(header)
    lines.append("---+-------------------------------")
    for ch in sorted(channels_values.keys(), key=int):
        vals = channels_values[ch]
        if vals:
            s = ", ".join([f"{v:.{precision}f}" for v in vals])
        else:
            s = "(none)"
        lines.append(f"{ch:>2} | {s}")
    return "\n".join(lines)


def run_calibrator(args):
    spi = SPI.SpiDev(SPI_PORT, SPI_DEVICE)
    spi.set_clock_hz(1350000)
    spi.mode = 0b00
    mcp = Adafruit_MCP3008.MCP3008(spi=spi)

    sample_interval = 1.0 / args.rate
    window_size = max(3, int(args.settle_window * args.rate))
    settle_thresh = args.settle_threshold
    cluster_tol = args.cluster_tol

    ch_cals = [ChannelCalibrator(ch, args.vref, args.adc_vref, window_size, settle_thresh, cluster_tol) for ch in range(8)]

    stop_event = threading.Event()

    def wait_enter():
        try:
            # wait for a single Enter press
            input()
        except Exception:
            pass
        stop_event.set()

    t = threading.Thread(target=wait_enter, daemon=True)
    t.start()

    hide_cursor = "\x1b[?25l"
    show_cursor = "\x1b[?25h"
    move_home = "\x1b[H"
    clear_screen = "\x1b[2J"

    sys.stdout.write(clear_screen)
    sys.stdout.write(hide_cursor)
    sys.stdout.flush()

    try:
        last_draw = 0
        while not stop_event.is_set():
            start = time.perf_counter()
            # sample all channels
            samples = [mcp.read_adc(ch) for ch in range(8)]
            for ch in range(8):
                ch_cals[ch].push_adc(samples[ch])
                ch_cals[ch].maybe_register()

            # redraw at ~10 Hz or when stopped
            if time.perf_counter() - last_draw >= 0.1:
                last_draw = time.perf_counter()
                # build display
                lines = []
                lines.append(f"MCP3008 calibrator - sampling {args.rate:.1f} Hz, settle_window={args.settle_window}s, threshold={settle_thresh}V")
                lines.append("Press Enter to finish and save calibration file.\n")
                for ch in range(8):
                    c = ch_cals[ch]
                    med, r = c.window_stats()
                    cur = f"{med:.{args.precision}f}" if med is not None else "n/a"
                    settled = "yes" if (r is not None and r <= settle_thresh) else "no"
                    pos_vals = c.get_positions_values()
                    pos_str = ", ".join([f"{v:.{args.precision}f}" for v in pos_vals]) if pos_vals else "(none)"
                    r_str = f"{r:.3f}" if r is not None else "n/a"
                    lines.append(f"CH{ch}: cur={cur} range={r_str} settled={settled}  positions=[{pos_str}]")

                # write to terminal in place
                sys.stdout.write(move_home + "\x1b[J")
                sys.stdout.write("\n".join(lines))
                sys.stdout.flush()

            # sleep remainder
            elapsed = time.perf_counter() - start
            to_sleep = sample_interval - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)

    except KeyboardInterrupt:
        stop_event.set()
    finally:
        sys.stdout.write(show_cursor + "\n")
        sys.stdout.flush()

    # collect results
    channels_values = {str(ch): ch_cals[ch].get_positions_values() for ch in range(8)}

    out = {
        "vref": args.vref,
        "adc_vref": args.adc_vref if args.adc_vref is not None else args.vref,
        "channels": channels_values,
        "meta": {
            "sample_rate": args.rate,
            "settle_window": args.settle_window,
            "settle_threshold": args.settle_threshold,
            "cluster_tol": args.cluster_tol,
        }
    }

    try:
        with open(args.outfile, 'w') as f:
            json.dump(out, f, indent=2)
        sys.stdout.write(f"Wrote calibration to {args.outfile}\n")
    except Exception as e:
        sys.stderr.write(f"Failed to write calibration file: {e}\n")

    # show final report table
    print()
    print(human_table(channels_values, precision=args.precision))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Calibrate MCP3008 channels by recording settled voltages per position.')
    parser.add_argument('--outfile', '-o', type=str, default='mcp3008_calibration.json', help='Output JSON calibration file')
    parser.add_argument('--rate', type=float, default=50.0, help='Sampling rate in Hz')
    parser.add_argument('--vref', type=float, default=3.3, help='Display/reference voltage')
    parser.add_argument('--adc-vref', type=float, default=None, help='Hardware ADC reference (if different)')
    parser.add_argument('--settle-window', type=float, default=0.25, help='Seconds worth of samples to consider for settling')
    parser.add_argument('--settle-threshold', type=float, default=0.02, help='Maximum window range (V) to treat as settled')
    parser.add_argument('--cluster-tol', type=float, default=0.05, help='Tolerance (V) to merge nearby settled values into same position')
    parser.add_argument('--precision', type=int, default=3, help='Decimal places in reports')
    args = parser.parse_args()

    print("Starting calibrator. Manipulate knobs/buttons; press Enter when done.")
    run_calibrator(args)

#!/usr/bin/env python3
"""
Picker knob calibrator.

Interactive calibration tool for picker knobs. Samples ADC values while you 
manipulate knobs through their full range, detects stable positions, and 
generates a calibration file for accurate position mapping.

Usage:
    python picker/calibrate.py --outfile picker_calibration.json

Follow the on-screen instructions to move each knob through all positions.
Press Enter when done to save the calibration file.
"""

import argparse
import sys
import time
import threading
import collections
import json
from typing import Dict, List, Optional

# Import the hardware interface
from picker.hw import HW, Calibration


def median(xs):
    """Calculate median of a list."""
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


class KnobCalibrator:
    """Calibrates a single knob channel by detecting stable voltage positions.

    This calibrator can require multiple consecutive settled windows before
    accepting a position. That makes the interactive calibration tool less
    sensitive to quick sweeps and accidental jitter. The confirmation count is
    configurable via the CLI argument --settle-confirm and only affects the
    calibration tool (does not change runtime mapping behavior).
    """
    
    def __init__(self, ch_index: int, vref: float = 3.3, window_size: int = 10, 
                 settle_thresh: float = 0.02, cluster_tol: float = 0.05, confirm_required: int = 3):
        self.ch = ch_index
        self.vref = vref
        self.window = collections.deque(maxlen=window_size)
        self.settle_thresh = settle_thresh
        self.cluster_tol = cluster_tol
        # Number of consecutive settled windows required to confirm a new
        # position during calibration. This slows detection (by design) and is
        # only used by the calibrator.
        self.confirm_required = max(1, int(confirm_required))
        # internal consecutive settled window counter and last median used for
        # stability checks.
        self._consecutive_settled = 0
        self._last_median = None
        # detected positions: list of (voltage, count) for incremental averaging
        self.positions = []
        self.last_reported = None

    def push_voltage(self, voltage: float):
        """Add a voltage reading to the sliding window."""
        self.window.append(voltage)

    def window_stats(self):
        """Get median voltage and range from current window."""
        if not self.window:
            return None, None
        mn = min(self.window)
        mx = max(self.window)
        med = median(list(self.window))
        return med, (mx - mn)

    def maybe_register_position(self):
        """Check if window is settled and register position if so."""
        med, voltage_range = self.window_stats()
        if med is None:
            return None
            
        # Consider settled if voltage range is within threshold
        if voltage_range <= self.settle_thresh:
            # Check if this median is consistent with the previous settled
            # median (within cluster tolerance). If so, increment the
            # consecutive settled-window counter; otherwise start over at one.
            if self._last_median is None or abs(self._last_median - med) <= self.cluster_tol:
                self._consecutive_settled += 1
            else:
                self._consecutive_settled = 1
            self._last_median = med

            # Only register the position after we've seen the required number
            # of consecutive settled windows. This reduces false positives
            # during quick sweeps.
            if self._consecutive_settled >= self.confirm_required:
                # Try to cluster with existing positions
                for i, (pos_voltage, count) in enumerate(self.positions):
                    if abs(pos_voltage - med) <= self.cluster_tol:
                        # Update running average
                        new_count = count + 1
                        new_voltage = (pos_voltage * count + med) / new_count
                        self.positions[i] = (new_voltage, new_count)
                        self.last_reported = new_voltage
                        # reset consecutive counter so we don't repeatedly add
                        self._consecutive_settled = 0
                        return new_voltage

                # New position - add it
                self.positions.append((med, 1))
                self.last_reported = med
                self._consecutive_settled = 0
                return med
            # otherwise, not yet confirmed
            return None
        else:
            # Not settled; reset confirmation state
            self._consecutive_settled = 0
            self._last_median = None
            self.last_reported = None
            return None

    def get_position_voltages(self) -> List[float]:
        """Get sorted list of detected position voltages."""
        voltages = [voltage for voltage, count in self.positions]
        return sorted(voltages)


def run_calibrator(args):
    """Run the interactive calibration process."""
    
    # Initialize hardware
    try:
        hw = HW(adc_spi_port=args.adc_spi_port, adc_spi_device=args.adc_spi_device)
    except Exception as e:
        print(f"Failed to initialize hardware: {e}")
        return 1

    # Setup calibrators for knob channels
    sample_interval = 1.0 / args.rate
    window_size = max(3, int(args.settle_window * args.rate))
    
    calibrators = {}
    for ch in hw.KNOB_CHANNELS:
        calibrators[ch] = KnobCalibrator(
            ch, args.vref, window_size, args.settle_threshold, args.cluster_tol,
            confirm_required=args.settle_confirm
        )

    # Setup threading for Enter detection
    stop_event = threading.Event()

    def wait_for_enter():
        try:
            input()
        except Exception:
            pass
        stop_event.set()

    enter_thread = threading.Thread(target=wait_for_enter, daemon=True)
    enter_thread.start()

    # Terminal control codes
    hide_cursor = "\x1b[?25l"
    show_cursor = "\x1b[?25h"
    move_home = "\x1b[H"
    clear_screen = "\x1b[2J"

    print("Picker Knob Calibrator")
    print("=" * 50)
    print("Instructions:")
    print("1. Slowly move each knob through ALL positions")
    print("2. Hold each position steady for ~1 second")
    print("3. Repeat for all 6 knobs (CH0, CH1, CH2, CH4, CH5, CH6)")
    print("4. Press Enter when finished")
    print()
    print("Starting calibration...")
    time.sleep(2)

    sys.stdout.write(clear_screen)
    sys.stdout.write(hide_cursor)
    sys.stdout.flush()

    try:
        last_draw = 0
        sample_count = 0
        
        while not stop_event.is_set():
            start_time = time.perf_counter()
            
            # Read all knob positions
            try:
                positions = hw.read_positions()
                
                # Convert to voltages and feed to calibrators
                for ch in hw.KNOB_CHANNELS:
                    raw_adc = hw.read_raw(ch)
                    voltage = (raw_adc / 1023.0) * args.vref
                    calibrators[ch].push_voltage(voltage)
                    calibrators[ch].maybe_register_position()
                    
                sample_count += 1
                
            except Exception as e:
                print(f"Sampling error: {e}")
                continue

            # Update display periodically
            if time.perf_counter() - last_draw >= 0.1:
                last_draw = time.perf_counter()
                
                # Build status display
                lines = []
                lines.append(f"Picker Calibration - {sample_count} samples at {args.rate:.1f} Hz")
                lines.append("Move knobs through all positions. Press Enter when done.")
                lines.append("")
                
                for ch in sorted(hw.KNOB_CHANNELS):
                    cal = calibrators[ch]
                    med, voltage_range = cal.window_stats()
                    
                    current = f"{med:.3f}V" if med is not None else "n/a"
                    settled = "YES" if (voltage_range is not None and voltage_range <= args.settle_threshold) else "no"
                    range_str = f"{voltage_range:.3f}V" if voltage_range is not None else "n/a"
                    
                    positions = cal.get_position_voltages()
                    pos_str = ", ".join([f"{v:.3f}" for v in positions]) if positions else "(none)"
                    
                    lines.append(f"CH{ch}: {current} (range: {range_str}, settled: {settled})")
                    lines.append(f"      Positions: [{pos_str}]")
                
                # Update terminal
                sys.stdout.write(move_home + "\x1b[J")
                sys.stdout.write("\n".join(lines))
                sys.stdout.flush()

            # Sleep for remainder of sample interval
            elapsed = time.perf_counter() - start_time
            sleep_time = sample_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        stop_event.set()
    finally:
        sys.stdout.write(show_cursor + "\n")
        sys.stdout.flush()

    # Collect calibration results
    channels_data = {}
    for ch in hw.KNOB_CHANNELS:
        positions = calibrators[ch].get_position_voltages()
        if positions:
            channels_data[str(ch)] = positions

    # Build calibration file
    cal_data = {
        "vref": args.vref,
        "adc_vref": args.vref,
        "channels": channels_data,
        "meta": {
            "sample_rate": args.rate,
            "settle_window": args.settle_window,
            "settle_threshold": args.settle_threshold,
            "cluster_tol": args.cluster_tol,
            "tool": "picker_calibrator"
        }
    }

    # Save calibration file
    try:
        with open(args.outfile, 'w') as f:
            json.dump(cal_data, f, indent=2)
        print(f"\nCalibration saved to: {args.outfile}")
    except Exception as e:
        print(f"\nError saving calibration: {e}")
        return 1

    # Print summary table
    print("\nCalibration Summary:")
    print("=" * 50)
    for ch in sorted(hw.KNOB_CHANNELS):
        positions = channels_data.get(str(ch), [])
        if positions:
            pos_str = ", ".join([f"{v:.3f}" for v in positions])
            print(f"CH{ch}: {len(positions)} positions - [{pos_str}]")
        else:
            print(f"CH{ch}: No positions detected")

    print(f"\nTo use this calibration:")
    print(f"python picker/run_picker.py --calibration {args.outfile}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description='Calibrate picker knobs')
    parser.add_argument('--outfile', '-o', default='picker_calibration.json',
                        help='Output calibration file (default: picker_calibration.json)')
    parser.add_argument('--rate', type=float, default=50.0,
                        help='Sampling rate in Hz (default: 50)')
    parser.add_argument('--vref', type=float, default=3.3,
                        help='Reference voltage (default: 3.3)')
    parser.add_argument('--settle-window', type=float, default=0.25,
                        help='Window size in seconds for stability detection (default: 0.25)')
    parser.add_argument('--settle-threshold', type=float, default=0.02,
                        help='Maximum voltage range to consider settled (default: 0.02)')
    parser.add_argument('--cluster-tol', type=float, default=0.05,
                        help='Voltage tolerance for clustering positions (default: 0.05)')
    parser.add_argument('--settle-confirm', type=int, default=3,
                        help='Number of consecutive settled windows required to confirm a position during calibration (default: 3). This only affects the calibration tool.')
    parser.add_argument('--adc-spi-port', type=int, default=0,
                        help='SPI port for ADC (default: 0)')
    parser.add_argument('--adc-spi-device', type=int, default=1,
                        help='SPI device for ADC (default: 1, CE1)')
    
    args = parser.parse_args()
    return run_calibrator(args)


if __name__ == "__main__":
    sys.exit(main())
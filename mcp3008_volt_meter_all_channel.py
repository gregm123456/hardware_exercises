#!/usr/bin/env python3
import Adafruit_MCP3008
import Adafruit_GPIO.SPI as SPI
import time
import json
import os
import argparse
import collections
import sys
import math
import signal

# Hardware SPI configuration:
SPI_PORT = 0
SPI_DEVICE = 1  # CE1


def main():
    parser = argparse.ArgumentParser(
        description="Live terminal bar-graph display for all 8 MCP3008 inputs."
    )
    parser.add_argument("--continuous", action="store_true", help="Run continuously (live display).")
    parser.add_argument("--interval", type=float, default=None, help="Seconds between display updates.")
    parser.add_argument("--rate", type=float, default=None, help="Updates per second (overrides --interval).")
    parser.add_argument("--duration", type=float, default=None, help="Total seconds to run when --continuous.")
    parser.add_argument("--avg", type=int, default=1, help="Number of samples to average per channel.")
    parser.add_argument("--vref", type=float, default=3.3, help="Reference voltage for ADC conversion.")
    parser.add_argument("--adc-vref", type=float, default=None, help="Hardware ADC reference voltage (if different from display vref).")
    parser.add_argument("--cal-file", type=str, default=None, help="Path to per-channel calibration JSON file.")
    parser.add_argument("--cal-mode", type=str, choices=("discrete","interp"), default="discrete", help="Calibration mapping mode: 'discrete' uses mid-point boundaries between recorded positions; 'interp' linearly interpolates between positions.")
    parser.add_argument("--bars", type=int, default=11, help="Height (rows) of the vertical bar graph.")
    parser.add_argument("--width", type=int, default=4, help="Width (chars) per channel column.")
    parser.add_argument("--precision", type=int, default=2, help="Decimal places for voltage display.")
    parser.add_argument("--ascii", action="store_true", help="Use ASCII characters instead of block glyphs.")
    args = parser.parse_args()

    # Determine interval between reports
    if args.rate is not None and args.rate > 0:
        interval = 1.0 / args.rate
    elif args.interval is not None:
        interval = float(args.interval)
    else:
        interval = 0.5  # default half-second updates

    # SPI setup like single-channel script
    spi = SPI.SpiDev(SPI_PORT, SPI_DEVICE)
    spi.set_clock_hz(1350000)
    spi.mode = 0b00
    mcp = Adafruit_MCP3008.MCP3008(spi=spi)

    # averaging buffers, one deque per channel
    avg = max(1, args.avg)
    bufs = [collections.deque(maxlen=avg) for _ in range(8)]

    # choose bar character(s)
    full_char = '#' if args.ascii else "█"
    empty_char = " "  # blank space

    # check for encoding support for block characters and fallback if needed
    if not args.ascii:
        try:
            '█'.encode(sys.stdout.encoding)
        except (UnicodeEncodeError, TypeError):
            full_char = '#'

    hide_cursor = "\x1b[?25l"
    show_cursor = "\x1b[?25h"
    move_home = "\x1b[H"
    clear_screen = "\x1b[2J"

    def read_all_once():
        return [mcp.read_adc(ch) for ch in range(8)]

    # load optional per-channel calibration map (simple gain/offset on voltage)
    cal_map = None
    if args.cal_file:
        try:
            with open(args.cal_file, 'r') as f:
                raw_cal = json.load(f)
                # normalize into a per-channel dict where each channel key maps to a dict
                # either {'gain':..., 'offset':...} or {'positions': [v0, v1, ...]}
                cal_map = {}
                # support both top-level 'channels' key or direct numeric keys
                source = raw_cal.get('channels', raw_cal) if isinstance(raw_cal, dict) else raw_cal
                if isinstance(source, dict):
                    for k, v in source.items():
                        try:
                            ch_idx = int(k)
                        except Exception:
                            continue
                        # if v is a dict with gain/offset, keep them
                        if isinstance(v, dict):
                            # if dict contains numeric list under some key, treat as positions
                            if 'positions' in v and isinstance(v['positions'], list):
                                cal_map[str(ch_idx)] = {'positions': [float(x) for x in v['positions']]}
                            else:
                                cal_map[str(ch_idx)] = {'gain': float(v.get('gain', 1.0)), 'offset': float(v.get('offset', 0.0))}
                        elif isinstance(v, list):
                            # list of measured voltages
                            cal_map[str(ch_idx)] = {'positions': [float(x) for x in v]}
                        else:
                            # unknown format; ignore
                            continue
                else:
                    # not a dict - can't interpret
                    cal_map = None
        except Exception as e:
            sys.stderr.write(f"Warning: couldn't load calibration file {args.cal_file}: {e}\n")
            cal_map = None

    # helper: compute normalized (0..1) value for calibrated binning
    def calibrated_norm(ch, v):
        # ch is index int, v is voltage
        if not cal_map:
            return clamp01(v / args.vref)
        ch_key = str(ch)
        entry = None
        if 'channels' in cal_map and ch_key in cal_map['channels']:
            entry = cal_map['channels'][ch_key]
        elif ch_key in cal_map:
            entry = cal_map[ch_key]

        if entry is None:
            return clamp01(v / args.vref)

        # positions list: map to nearest position index (bin)
        if 'positions' in entry:
            pos = entry['positions']
            if not pos:
                return clamp01(v / args.vref)
            # ensure positions are sorted ascending for midpoint logic
            pos_sorted = sorted(pos)
            n = len(pos_sorted)
            if n == 1:
                return 0.0
            # discrete mode: use midpoints between adjacent recorded positions as boundaries
            if args.cal_mode == 'discrete':
                mid = [(pos_sorted[i] + pos_sorted[i+1]) / 2.0 for i in range(n-1)]
                # find first midpoint greater than v -> that index is the bin
                bin_idx = None
                for i, m in enumerate(mid):
                    if v < m:
                        bin_idx = i
                        break
                if bin_idx is None:
                    bin_idx = n - 1
                return clamp01(bin_idx / float(n - 1))
            else:
                # interp mode: linearly interpolate between recorded positions
                # if below first or above last, clamp
                if v <= pos_sorted[0]:
                    return 0.0
                if v >= pos_sorted[-1]:
                    return 1.0
                # find interval
                for i in range(n - 1):
                    a = pos_sorted[i]
                    b = pos_sorted[i+1]
                    if a <= v <= b:
                        frac = (v - a) / (b - a) if b != a else 0.0
                        # overall normalized position across full span
                        return clamp01((i + frac) / float(n - 1))
                return clamp01(v / args.vref)

        # fallback: apply gain/offset if present and normalize
        try:
            gain = float(entry.get('gain', 1.0))
            offset = float(entry.get('offset', 0.0))
            v2 = gain * v + offset
            return clamp01(v2 / args.vref)
        except Exception:
            return clamp01(v / args.vref)

    def adc_to_voltage(adc_val, ch=None):
        # Use hardware ADC reference if provided, else default to display vref
        ref = args.adc_vref if args.adc_vref is not None else args.vref
        v = (adc_val / 1023.0) * ref
        # apply per-channel calibration if available: expect {"channels": {"0": {"gain":.., "offset":..}, ...}}
        if cal_map and ch is not None:
            try:
                ch_key = str(ch)
                entry = None
                if isinstance(cal_map, dict):
                    if 'channels' in cal_map and ch_key in cal_map['channels']:
                        entry = cal_map['channels'][ch_key]
                    elif ch_key in cal_map:
                        entry = cal_map[ch_key]
                if entry:
                    gain = float(entry.get('gain', 1.0))
                    offset = float(entry.get('offset', 0.0))
                    v = gain * v + offset
            except Exception:
                pass
        return v

    def clamp01(x):
        return max(0.0, min(1.0, x))

    def render(adc_counts):
        # adc_counts: list of 8 raw ADC values (0..1023)
        # Compute bar levels based on calibrated ADC voltage and display vref
        levels = []
        for ch, a in enumerate(adc_counts):
            v = adc_to_voltage(a, ch=ch)
            # if calibration provides discrete positions for this channel, map to nearest bin
            norm = calibrated_norm(ch, v)
            levels.append(int(round(norm * args.bars)))

        out_lines = []

        # vertical bars: from top row (bars) down to 1
        for row in range(args.bars, 0, -1):
            cols = []
            for lvl in levels:
                if lvl >= row:
                    cols.append(full_char * args.width)
                else:
                    cols.append(empty_char * args.width)
            out_lines.append(" ".join(cols))

        # channel labels
        labels = [f"CH{ch}".center(args.width) for ch in range(8)]
        out_lines.append(" ".join(labels))

        # voltage values (render using vref)
        volt_vals = []
        for ch, a in enumerate(adc_counts):
            v = adc_to_voltage(a, ch=ch)
            s = f"{v:.{args.precision}f}"
            volt_vals.append(s.center(args.width))
        out_lines.append(" ".join(volt_vals))

        # footer with vref and timestamp
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        footer = f"vref={args.vref:.3f}V  interval={interval:.3f}s  {ts}"
        out_lines.append(footer)

        # compose and write
        # move home, then clear from cursor to end of screen
        sys.stdout.write(move_home + "\x1b[J")
        sys.stdout.write("\n".join(out_lines))
        sys.stdout.flush()

    # cleanup handler to restore cursor
    def cleanup_and_exit(signum=None, frame=None):
        sys.stdout.write("\n")
        sys.stdout.write(show_cursor)
        sys.stdout.flush()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup_and_exit)
    signal.signal(signal.SIGTERM, cleanup_and_exit)

    # single-shot or continuous
    if args.continuous:
        # prepare screen
        sys.stdout.write(clear_screen)
        sys.stdout.write(hide_cursor)
        sys.stdout.write(move_home)
        sys.stdout.flush()

        start = time.perf_counter()
        next_report = start

        try:
            while True:
                now = time.perf_counter()

                # sample all channels once
                raw = read_all_once()
                for ch in range(8):
                    bufs[ch].append(raw[ch])

                # compute averaged raw ADC counts
                averaged = []
                for ch in range(8):
                    if len(bufs[ch]) > 0:
                        avg_adc = sum(bufs[ch]) / len(bufs[ch])
                    else:
                        avg_adc = 0.0
                    averaged.append(avg_adc)

                if now >= next_report:
                    render(averaged)
                    next_report += interval

                    # duration check
                    if args.duration is not None and (now - start) >= args.duration:
                        break

                # tiny sleep to avoid pegging CPU
                # sleep just enough to fill the remainder of the interval
                sleep_duration = interval - (time.perf_counter() - now)
                if sleep_duration > 0:
                    time.sleep(sleep_duration)
        except KeyboardInterrupt:
            pass
        finally:
            sys.stdout.write("\n")
            sys.stdout.write(show_cursor)
            sys.stdout.flush()
    else:
        # single-shot report of all channels
        raw = read_all_once()
        vals = []
        for ch in range(8):
            if avg > 1:
                # take additional samples for averaging
                samples = [mcp.read_adc(ch) for _ in range(avg - 1)]
                all_samples = [raw[ch]] + samples
                adc_val = sum(all_samples) / len(all_samples)
            else:
                adc_val = raw[ch]
            vals.append(adc_val)
        # print simple vertical-ish display once (pass raw ADC counts)
        render(vals)


if __name__ == "__main__":
    main()
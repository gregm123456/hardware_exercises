#!/usr/bin/env python3
import Adafruit_MCP3008
import Adafruit_GPIO.SPI as SPI
import time
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
    parser.add_argument("--bars", type=int, default=12, help="Height (rows) of the vertical bar graph.")
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

    def adc_to_voltage(adc_val):
        return (adc_val / 1023.0) * args.vref

    def clamp01(x):
        return max(0.0, min(1.0, x))

    def render(voltages):
        # voltages: list of 8 floats
        # normalized levels 0..1
        norms = [clamp01(v / args.vref) for v in voltages]
        levels = [int(round(n * args.bars)) for n in norms]  # 0..bars

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

        # voltage values
        volt_vals = []
        for v in voltages:
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

        print(f"DEBUG: continuous mode. interval={interval}, duration={args.duration}", file=sys.stderr)

        try:
            while True:
                now = time.perf_counter()

                # sample all channels once
                raw = read_all_once()
                print(f"DEBUG: raw adc values: {raw}", file=sys.stderr)
                for ch in range(8):
                    bufs[ch].append(raw[ch])

                # compute averaged voltages
                averaged = []
                for ch in range(8):
                    if len(bufs[ch]) > 0:
                        avg_adc = sum(bufs[ch]) / len(bufs[ch])
                    else:
                        avg_adc = 0.0
                    averaged.append(adc_to_voltage(avg_adc))

                if now >= next_report:
                    print(f"DEBUG: reporting. now={now:.4f}, next_report={next_report:.4f}", file=sys.stderr)
                    render(averaged)
                    next_report += interval

                    # duration check
                    if args.duration is not None and (now - start) >= args.duration:
                        print(f"DEBUG: duration met. now-start={(now-start):.4f}", file=sys.stderr)
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
                samples = [mcp.read_adc(ch) for _ in range(avg)]
                adc_val = sum(samples) / len(samples)
            else:
                adc_val = raw[ch]
            vals.append(adc_to_voltage(adc_val))
        # print simple vertical-ish display once
        render(vals)


if __name__ == "__main__":
    main()
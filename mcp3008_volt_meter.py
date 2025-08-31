import Adafruit_MCP3008
import Adafruit_GPIO.SPI as SPI
import time
import argparse
import collections
import sys

# Hardware SPI configuration:
SPI_PORT   = 0
SPI_DEVICE = 1  # CE1


def main():
    """Main function to read voltage from MCP3008 with high-rate continuous scanning."""
    parser = argparse.ArgumentParser(description='Read voltage from MCP3008 ADC.')
    parser.add_argument('--continuous', action='store_true', help='Enable continuous reading.')
    parser.add_argument('--interval', type=float, default=None, help='Time interval between readings in seconds.')
    parser.add_argument('--rate', type=float, default=None, help='Readings per second (overrides --interval).')
    parser.add_argument('--duration', type=float, default=None, help='Total seconds to run when --continuous (optional).')
    parser.add_argument('--avg', type=int, default=1, help='Number of samples to average for each reported reading.')
    parser.add_argument('--volts-only', action='store_true', help='Output only the voltage value.')
    parser.add_argument('--vref', type=float, default=3.3, help='Reference voltage for the ADC.')
    parser.add_argument('--inplace', action='store_true', help='Print updates in-place (carriage return).')
    parser.add_argument('--precision', type=int, default=3, help='Decimal places for voltage output.')

    args = parser.parse_args()

    # Determine interval (seconds) between reported outputs
    if args.rate is not None and args.rate > 0:
        interval = 1.0 / args.rate
    elif args.interval is not None:
        interval = float(args.interval)
    else:
        interval = 1.0  # default 1 second

    # Create SPI object using Adafruit GPIO wrapper expected by Adafruit_MCP3008
    spi = SPI.SpiDev(SPI_PORT, SPI_DEVICE)
    spi.set_clock_hz(1350000)
    spi.mode = 0b00

    mcp = Adafruit_MCP3008.MCP3008(spi=spi)

    # simple rolling buffer for averaging if requested
    buf = collections.deque(maxlen=args.avg)

    def read_adc_once():
        return mcp.read_adc(0)

    def adc_to_voltage(adc_val):
        return (adc_val / 1023.0) * args.vref

    if args.continuous:
        start = time.perf_counter()
        next_report = start
        count = 0
        try:
            while True:
                now = time.perf_counter()

                # sample as fast as possible until next report time (to allow internal averaging)
                adc = read_adc_once()
                if args.avg > 1:
                    buf.append(adc)
                    averaged = sum(buf) / len(buf)
                else:
                    averaged = adc

                # If it's time to report, print the averaged value
                if now >= next_report:
                    voltage = adc_to_voltage(averaged)
                    if args.inplace:
                        if args.volts_only:
                            sys.stdout.write(f'\r{voltage:.{args.precision}f}V')
                        else:
                            sys.stdout.write(f"\rVoltage: {voltage:.{args.precision}f}V")
                        sys.stdout.flush()
                    else:
                        if args.volts_only:
                            print(f"{voltage:.{args.precision}f}")
                        else:
                            print(f"Raw ADC Value: {int(averaged)}\tVoltage: {voltage:.{args.precision}f}V")

                    count += 1
                    next_report += interval

                    # optional duration stop
                    if args.duration is not None and (now - start) >= args.duration:
                        break

                # sleep a tiny bit to avoid 100% CPU if sampling very fast
                time.sleep(0.0005)
        except KeyboardInterrupt:
            pass
        finally:
            if args.inplace:
                print()  # newline after in-place updates
    else:
        # single-shot
        if args.avg > 1:
            vals = [read_adc_once() for _ in range(args.avg)]
            value = sum(vals) / len(vals)
        else:
            value = read_adc_once()
        voltage = adc_to_voltage(value)
        if args.volts_only:
            print(f"{voltage:.{args.precision}f}")
        else:
            print(f"Raw ADC Value: {int(value)}")
            print(f"Voltage: {voltage:.{args.precision}f}V")


if __name__ == '__main__':
    main()

"""CLI runner for the picker app.

Provides --simulate and --config options. In simulate mode, uses SimulatedMCP3008.
"""
import argparse
import signal
import sys
import logging
import time

from picker.hw import HW, SimulatedMCP3008, Calibration
from picker.config import load_texts, DEFAULT_DISPLAY
from picker.core import PickerCore
from picker.ui import compose_message, compose_overlay
from picker.drivers.display_fast import blit

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main(argv=None):
    p = argparse.ArgumentParser(description="Run the picker application")
    p.add_argument("--simulate", action="store_true", help="Run with simulated ADC values")
    p.add_argument("--config", help="Path to texts JSON config (defaults to picker/sample_texts.json)")
    p.add_argument("--display-w", type=int, default=1024)
    p.add_argument("--display-h", type=int, default=600)
    p.add_argument("--adc-spi-port", type=int, default=0, help="SPI port for ADC/MCP3008 (default 0)")
    p.add_argument("--adc-spi-device", type=int, default=1, help="SPI device (CE) for ADC/MCP3008 - CE1 (default 1)")
    p.add_argument("--display-spi-device", type=int, default=0, help="SPI device (CE) for e-paper display - CE0 (default 0)")
    p.add_argument("--rotate", choices=['CW','CCW','flip','none'], default='CW', help="Rotate display output: CW, CCW, flip, or none")
    p.add_argument("--force-simulation", action="store_true", help="Force display simulation mode")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    p.add_argument("--calibration", type=str, help="Path to knob calibration JSON file")
    args = p.parse_args(argv)
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")
    
    logger.info(f"Starting picker - ADC on CE{args.adc_spi_device}, Display on CE{args.display_spi_device}")
    
    texts = load_texts(args.config) if args.config else load_texts()

    if args.simulate:
        logger.info("Using simulated ADC")
        adc = SimulatedMCP3008()
    else:
        logger.info("Using hardware ADC")
        adc = None  # real ADC reader to be implemented / wired here

    calib_map = {ch: Calibration() for ch in range(8)}
    
    try:
        hw = HW(adc_reader=adc, calib_map=calib_map, adc_spi_port=args.adc_spi_port, adc_spi_device=args.adc_spi_device, calib_file=args.calibration)
        logger.info("Hardware interface initialized")
    except Exception as e:
        logger.error(f"Failed to initialize hardware: {e}")
        return 1

    try:
        core = PickerCore(
            hw, 
            texts, 
            display_size=(args.display_w, args.display_h),
            spi_device=args.display_spi_device,
            force_simulation=args.force_simulation,
            rotate=(None if args.rotate == 'none' else args.rotate)
        )
        logger.info("Picker core initialized")
    except Exception as e:
        logger.error(f"Failed to initialize picker core: {e}")
        return 1

    # Show a startup message for 2 seconds, then clear the screen
    try:
        logger.info("Displaying startup message")
        img = compose_message("Starting...", full_screen=(args.display_w, args.display_h))
        blit(img, "starting", rotate=(None if args.rotate == 'none' else args.rotate))
        time.sleep(2.0)
        # clear by drawing an empty overlay/background
        logger.info("Clearing startup message")
        clear_img = compose_overlay("", [""] * 12, 0, full_screen=(args.display_w, args.display_h))
        blit(clear_img, "clear_start", rotate=(None if args.rotate == 'none' else args.rotate))
        # Show the main placeholder screen immediately so the device isn't blank
        try:
            core.show_main()
        except Exception as e:
            logger.debug(f"show_main failed: {e}")
        logger.info("Ready - entering main loop")
    except Exception as e:
        # If display or PIL fails, continue silently to the main loop
        logger.warning(f"Startup display failed: {e} - continuing anyway")

    def handle_sigint(sig, frame):
        logger.info('Stopping picker application...')
        core.running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    
    try:
        core.run()
        return 0
    except Exception as e:
        logger.error(f"Main loop error: {e}")
        return 1


if __name__ == "__main__":
    main()

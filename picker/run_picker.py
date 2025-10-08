"""CLI runner for the picker app.

Provides --simulate and --config options. In simulate mode, uses SimulatedMCP3008.
"""
import argparse
import signal
import sys
import logging
import time
import atexit

from picker.hw import HW, SimulatedMCP3008, Calibration
from picker.config import load_texts, DEFAULT_DISPLAY
from picker.core import PickerCore
from picker.ui import compose_message, compose_overlay
from picker.drivers.display_fast import blit, clear_display, close

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
    p.add_argument("--run-calibrator", action="store_true",
                   help="Run the interactive calibrator before starting the picker (passes through settle-confirm)")
    p.add_argument("--calibrate-settle-confirm", type=int, default=None,
                   help="When running the calibrator via --run-calibrator, pass this as --settle-confirm to the calibrator. If omitted the calibrator default is used.")
    args = p.parse_args(argv)
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")
    
    logger.info(f"Starting picker - ADC on CE{args.adc_spi_device}, Display on CE{args.display_spi_device}")
    
    texts = load_texts(args.config) if args.config else load_texts()

    # If user requested to run the calibrator through run_picker, invoke it
    # here and optionally forward the settle-confirm value. Running the
    # calibrator is intentionally done before initializing the main HW/core so
    # the interactive tool can run standalone and the process exits after
    # calibration unless the user continues deliberately.
    if args.run_calibrator:
        try:
            import picker.calibrate as calibrate
            # Build a minimal args namespace for the calibrator
            class _A: pass
            cal_args = _A()
            # default outfile
            cal_args.outfile = 'picker_calibration.json'
            cal_args.rate = 50.0
            cal_args.vref = 3.3
            cal_args.settle_window = 0.25
            cal_args.settle_threshold = 0.02
            cal_args.cluster_tol = 0.05
            # if user provided a settle-confirm forward it
            cal_args.settle_confirm = args.calibrate_settle_confirm if args.calibrate_settle_confirm is not None else 3
            cal_args.adc_spi_port = args.adc_spi_port
            cal_args.adc_spi_device = args.adc_spi_device

            logger.info(f"Running interactive calibrator (confirm={cal_args.settle_confirm})")
            rc = calibrate.run_calibrator(cal_args)
            # If run_calibrator returns non-zero, log and exit with that code
            if rc not in (None, 0):
                logger.error(f"Calibrator exited with code {rc}")
                return int(rc)
            # After successful calibration, continue to start picker if the
            # user also supplied --calibration and wants to run immediately.
            # Otherwise exit so the user can re-run with --calibration.
            if not args.calibration:
                logger.info('Calibration complete; no --calibration file provided, exiting.')
                return 0
        except Exception as e:
            logger.error(f"Failed to run calibrator in-process: {e}")
            return 1

    if args.simulate:
        logger.info("Using simulated ADC")
        adc = SimulatedMCP3008()
    else:
        logger.info("Using hardware ADC")
        adc = None  # real ADC reader to be implemented / wired here

    # Build initial calibration map. Keep calibration inversion disabled
    # (default) and implement the traversal inversion at the UI layer so
    # calibration files remain compatible.
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

    # Show a startup message for 2 seconds. The startup image is full-screen
    # and the display driver performs a full update for 'auto' mode, so an
    # explicit initial clear is redundant on most hardware and can be skipped
    # to save time and extra flashes.
    try:
        logger.info("Displaying startup message")
        img = compose_message("Starting...", full_screen=(args.display_w, args.display_h))
        blit(img, "starting", rotate=(None if args.rotate == 'none' else args.rotate))
        time.sleep(1.0)
        # Directly show the main placeholder screen without an intermediate clear
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
        try:
            # try to blank the display before exiting
            logger.info('Clearing display before exit (SIGINT)')
            clear_display()
            # give the device a moment to finish any work (mirrors blank_screen.py)
            time.sleep(0.5)
            close()
        except Exception as e:
            logger.debug(f'Error while clearing display on SIGINT: {e}')
        sys.exit(0)

    def _cleanup_display():
        """Best-effort cleanup for display on normal exit or atexit."""
        try:
            logger.info('Running display cleanup at exit')
            clear_display()
            # give display time to complete clearing
            time.sleep(0.5)
            close()
        except Exception as e:
            logger.debug(f'Error during atexit display cleanup: {e}')

    # Ensure cleanup runs on normal process exit
    atexit.register(_cleanup_display)

    signal.signal(signal.SIGINT, handle_sigint)
    
    try:
        core.run()
        return 0
    except Exception as e:
        logger.error(f"Main loop error: {e}")
        return 1


if __name__ == "__main__":
    main()

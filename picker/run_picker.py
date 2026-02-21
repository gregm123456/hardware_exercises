"""CLI runner for the picker app.

Provides --simulate and --config options. In simulate mode, uses SimulatedMCP3008.
Provides --rotary mode for single GPIO rotary encoder + pushbutton navigation.
"""
import argparse
import signal
import sys
import logging
import time
import atexit

from picker.hw import HW, SimulatedMCP3008, Calibration
from picker.config import (
    load_texts, load_menus, DEFAULT_DISPLAY,
    DEFAULT_ROTARY_PIN_CLK, DEFAULT_ROTARY_PIN_DT, DEFAULT_ROTARY_PIN_SW,
    DEFAULT_ROTARY_DEBOUNCE_MS,
)
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


def _run_rotary(args) -> int:
    """Run the picker using a single GPIO rotary encoder + pushbutton.

    Loads menus from *args.config* (or the default sample file), initialises
    either a real :class:`~picker.rotary_encoder.RotaryEncoder` or a
    :class:`~picker.rotary_encoder.SimulatedRotaryEncoder`, then runs the
    :class:`~picker.rotary_core.RotaryPickerCore` event loop.
    """
    from picker.rotary_encoder import RotaryEncoder, SimulatedRotaryEncoder
    from picker.rotary_core import RotaryPickerCore
    from picker.ui import compose_rotary_menu, compose_message
    from picker.drivers.display_fast import init as display_init, blit, clear_display, close as display_close

    rotate = None if args.rotate == 'none' else args.rotate

    logger.info("Rotary encoder mode")
    try:
        menus = load_menus(args.config if args.config else None)
        logger.info(f"Loaded {len(menus)} menus from config")
        for i, (title, values) in enumerate(menus):
            logger.info(f"  Menu {i}: {title!r} with {len(values)} values: {values[:3]}{['...'] if len(values) > 3 else []}")
    except Exception as e:
        logger.error(f"Failed to load menus: {e}")
        return 1

    # Initialise encoder
    if args.rotary_simulate:
        logger.info("Using SimulatedRotaryEncoder (no hardware)")
        encoder = SimulatedRotaryEncoder()
    else:
        try:
            encoder = RotaryEncoder(
                pin_clk=args.rotary_clk,
                pin_dt=args.rotary_dt,
                pin_sw=args.rotary_sw,
                debounce_ms=args.rotary_debounce_ms,
            )
            logger.info(
                f"RotaryEncoder initialised: CLK={args.rotary_clk} "
                f"DT={args.rotary_dt} SW={args.rotary_sw} "
                f"debounce={args.rotary_debounce_ms}ms"
            )
        except Exception as e:
            logger.error(f"Failed to initialise RotaryEncoder: {e}")
            return 1

    # Initialise display
    display_ok = display_init(
        spi_device=args.display_spi_device,
        force_simulation=args.force_simulation,
        rotate=rotate,
    )
    if not display_ok:
        logger.warning("Display init failed - continuing in simulation mode")

    effective_size = (args.display_w, args.display_h)
    if rotate in ('CW', 'CCW'):
        effective_size = (args.display_h, args.display_w)

    # Track previous image for true partial refresh
    prev_menu_image = [None]  # Use list for mutability

    def _do_display(title, items, selected_index):
        """Render and blit a rotary menu image with partial refresh."""
        try:
            logger.info(f"[DISPLAY] title={title!r}, showing item {selected_index} of {len(items)}: {items[selected_index] if selected_index < len(items) else '?'}")
            img = compose_rotary_menu(title, items, selected_index, full_screen=effective_size)
            
            # Save current image to temp file for next partial update
            import tempfile
            tmp_path = tempfile.gettempdir() + "/picker_rotary_menu.png"
            img.save(tmp_path)
            
            # Use partial mode with previous image if available
            if prev_menu_image[0] is not None:
                blit(img, "rotary-menu", rotate, mode="partial", prev_image_path=prev_menu_image[0])
            else:
                # First display - use DU mode (fast 1-bit update)
                blit(img, "rotary-menu", rotate, mode="DU")
            
            prev_menu_image[0] = tmp_path
        except Exception as exc:
            logger.debug(f"Display update failed: {exc}")

    def _do_action(action_name):
        """Handle Go / Reset actions."""
        logger.info(f"Action triggered: {action_name}")
        try:
            msg = "GO!" if action_name == "Go" else "RESETTING"
            img = compose_message(msg, full_screen=effective_size)
            # Use full mode for action message (important status change)
            blit(img, action_name.lower(), rotate, "full")
            time.sleep(2.0)
            # Return to menu instead of staying stuck on action message
            title, items, idx = core.current_display()
            _do_display(title, items, idx)
        except Exception as exc:
            logger.debug(f"Action display failed: {exc}")

    core = RotaryPickerCore(
        menus=menus,
        on_display=_do_display,  # Direct display (no throttling needed with queue draining)
        on_action=_do_action,
        wrap=False,  # Disable wrap-around: stick at ends instead of wrapping to other end
    )

    # Show startup banner
    try:
        img = compose_message("Starting...", full_screen=effective_size)
        blit(img, "starting", rotate, "full")
        time.sleep(1.0)
    except Exception:
        pass

    # Refresh to show the actual menu after startup banner
    try:
        title, items, idx = core.current_display()
        _do_display(title, items, idx)
    except Exception as exc:
        logger.debug(f"Failed to refresh menu after startup: {exc}")

    logger.info("Rotary picker running — press Ctrl-C to stop")

    running = True
    event_count = 0
    last_log_time = time.time()
    cumulative_rotation = 0  # Track net rotation from queued events
    rotation_threshold = 2  # Require N detents to move 1 menu item (finer control)
    
    # Directional momentum filtering (noise rejection for fast rotation)
    rotation_history = []  # Recent rotation events for direction tracking
    history_window = 10  # Track last N events

    def _shutdown(sig, frame):
        nonlocal running
        logger.info("Shutting down rotary picker...")
        running = False

    def _cleanup():
        try:
            encoder.cleanup()
        except Exception:
            pass
        try:
            clear_display()
            time.sleep(0.5)
            display_close()
        except Exception:
            pass

    atexit.register(_cleanup)
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while running:
            # Drain ALL rotation events from queue and accumulate
            # This prevents "scrolling continues after knob stops" problem
            had_events = False
            button_event = None
            
            while True:
                event = encoder.get_event()
                if event is None:
                    break
                
                event_count += 1
                had_events = True
                kind, value = event
                
                if kind == "rotate":
                    rotation_value = int(value)
                    
                    # Directional momentum filtering: track recent events
                    rotation_history.append(rotation_value)
                    if len(rotation_history) > history_window:
                        rotation_history.pop(0)
                    
                    # Calculate dominant direction from recent history
                    if len(rotation_history) >= 3:
                        recent_sum = sum(rotation_history[-5:])  # Last 5 events
                        # If we have strong momentum in one direction, filter out noise
                        if abs(recent_sum) >= 3:  # Strong directional momentum
                            # Ignore events that oppose the momentum (likely noise)
                            if (recent_sum > 0 and rotation_value < 0) or (recent_sum < 0 and rotation_value > 0):
                                logger.debug(f"[Noise filter] Ignoring {rotation_value} event (momentum={recent_sum})")
                                continue  # Skip this noisy event
                    
                    cumulative_rotation += rotation_value
                    logger.debug(f"[Event #{event_count}] rotate={rotation_value}, cumulative={cumulative_rotation}")
                elif kind == "button":
                    button_event = bool(value)
                    logger.debug(f"[Event #{event_count}] button={value}")
            
            # Apply cumulative rotation with threshold (finer control)
            if cumulative_rotation != 0:
                # Calculate how many menu items to move (accumulator / threshold)
                movement = cumulative_rotation // rotation_threshold
                remainder = cumulative_rotation % rotation_threshold
                
                if movement != 0:
                    logger.debug(f"Applying rotation: {cumulative_rotation} detents -> {movement} items (remainder={remainder})")
                    core.handle_rotate(movement)
                    cumulative_rotation = remainder  # Keep remainder for next time
                    logger.debug(f"  -> After rotate: cursor={core.cursor}, remaining={cumulative_rotation}")
                else:
                    logger.debug(f"Rotation accumulated: {cumulative_rotation}/{rotation_threshold} (need {rotation_threshold - abs(cumulative_rotation)} more)")
            
            # Handle button event if any
            if button_event is not None:
                core.handle_button(button_event)
                logger.debug(f"  -> After button press={button_event}: state={core.state.name}, cursor={core.cursor}")
            
            # Small sleep to avoid busy-waiting
            if not had_events:
                time.sleep(0.001)
            
            # Log summary every 5 seconds
            now = time.time()
            if now - last_log_time >= 5.0:
                logger.info(f"Event loop: {event_count} events processed in last {now - last_log_time:.1f}s, current state={core.state.name} cursor={core.cursor}")
                event_count = 0
                last_log_time = now
    except Exception as e:
        logger.error(f"Rotary event loop error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    finally:
        _cleanup()

    return 0


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
    p.add_argument("--generation-mode", choices=['txt2img', 'img2img'], default='txt2img', help="Generation mode: txt2img (default) or img2img")
    p.add_argument("--calibration", type=str, help="Path to knob calibration JSON file")
    p.add_argument("--run-calibrator", action="store_true",
                   help="Run the interactive calibrator before starting the picker (passes through settle-confirm)")
    p.add_argument("--calibrate-settle-confirm", type=int, default=None,
                   help="When running the calibrator via --run-calibrator, pass this as --settle-confirm to the calibrator. If omitted the calibrator default is used.")
    p.add_argument("--stream", action="store_true", help="Enable live camera MJPEG stream")
    p.add_argument("--stream-port", type=int, default=8088, help="Port for live camera stream (default 8088)")

    # --- Rotary encoder mode ---
    rotary_group = p.add_argument_group(
        "Rotary encoder",
        "Use a single GPIO rotary encoder + pushbutton instead of six ADC knobs. "
        "Pass --rotary to enable; optionally override the BCM GPIO pin numbers below.",
    )
    rotary_group.add_argument(
        "--rotary",
        action="store_true",
        help="Enable single rotary encoder navigation (replaces ADC knobs)",
    )
    rotary_group.add_argument(
        "--rotary-simulate",
        action="store_true",
        help="Use SimulatedRotaryEncoder (no hardware required; for testing)",
    )
    rotary_group.add_argument(
        "--rotary-clk",
        type=int,
        default=DEFAULT_ROTARY_PIN_CLK,
        metavar="BCM_PIN",
        help=f"BCM GPIO pin for rotary CLK/A output (default {DEFAULT_ROTARY_PIN_CLK})",
    )
    rotary_group.add_argument(
        "--rotary-dt",
        type=int,
        default=DEFAULT_ROTARY_PIN_DT,
        metavar="BCM_PIN",
        help=f"BCM GPIO pin for rotary DT/B output (default {DEFAULT_ROTARY_PIN_DT})",
    )
    rotary_group.add_argument(
        "--rotary-sw",
        type=int,
        default=DEFAULT_ROTARY_PIN_SW,
        metavar="BCM_PIN",
        help=f"BCM GPIO pin for rotary SW (pushbutton, default {DEFAULT_ROTARY_PIN_SW})",
    )
    rotary_group.add_argument(
        "--rotary-debounce-ms",
        type=int,
        default=DEFAULT_ROTARY_DEBOUNCE_MS,
        metavar="MS",
        help=f"Button debounce time in ms (default {DEFAULT_ROTARY_DEBOUNCE_MS})",
    )

    args = p.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")

    # Dispatch to the rotary encoder runner if requested
    if args.rotary or args.rotary_simulate:
        return _run_rotary(args)

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
            rotate=(None if args.rotate == 'none' else args.rotate),
            generation_mode=args.generation_mode,
            stream=args.stream,
            stream_port=args.stream_port
        )
        logger.info("Picker core initialized")
        
        if args.stream:
            if core.camera_manager and getattr(core.camera_manager, "stream_port", None):
                port = core.camera_manager.stream_port
                import socket
                try:
                    # Try to get the local IP address
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.settimeout(0)
                    try:
                        # doesn't even have to be reachable
                        s.connect(('10.254.254.254', 1))
                        ip = s.getsockname()[0]
                    except Exception:
                        ip = '127.0.0.1'
                    finally:
                        s.close()
                    logger.info(f"LIVE STREAM AVAILABLE AT: http://{ip}:{port}/stream.mjpg")
                except Exception:
                    logger.info(f"Live stream enabled on port {port} (IP unknown)")
            else:
                logger.warning("Live stream was requested, but the MJPEG server did not start. Check earlier camera logs.")
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

    def handle_shutdown(sig, frame):
        logger.info('Stopping picker application...')
        core.running = False
        try:
            # try to blank the display before exiting
            logger.info('Clearing display before exit')
            clear_display()
            # give the device a moment to finish any work (mirrors blank_screen.py)
            time.sleep(0.5)
            close()
        except Exception as e:
            logger.debug(f'Error while clearing display on exit: {e}')
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

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        core.run()
        return 0
    except Exception as e:
        logger.error(f"Main loop error: {e}")
        return 1


if __name__ == "__main__":
    main()

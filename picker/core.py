"""Core state machine and event loop for the picker application.

This module is intentionally simple: it polls HW for knob changes and button presses,
invokes the UI composer, and routes output to the display adapter. It supports a
simulation mode when the HW instance is backed by `SimulatedMCP3008`.
"""
import time
import concurrent.futures
import threading
import logging
from typing import Dict, Tuple

from picker.hw import HW
from picker.ui import compose_overlay, compose_message, compose_main_screen
from picker.drivers.display_fast import init as display_init, blit, partial_update, full_update, clear_display
from picker.drivers.display_fast import get_display_size
from picker.config import load_texts, DEFAULT_DISPLAY

logger = logging.getLogger(__name__)


class PickerCore:
    def __init__(self, hw: HW, texts: Dict = None, display_size: Tuple[int, int] = (1024, 600), spi_device=0, force_simulation=False, rotate: str = 'CW'):
        self.hw = hw
        self.texts = texts or load_texts()
        self.display_size = display_size
        # If rotation will be applied, compose UI using the rotated dimensions
        if rotate in ('CW', 'CCW'):
            # swap width/height so composition matches final orientation
            self.effective_display_size = (display_size[1], display_size[0])
        else:
            self.effective_display_size = display_size

        self.overlay_visible = False
        self.overlay_timeout = 1.5  # seconds (default idle/menu clear timeout)
        # track last activity per knob channel so each knob keeps its own 2s timeout
        self.last_activity_per_knob = {}
        # current knob being shown as an overlay: tuple (ch, pos) or None
        self.current_knob = None

        # Lightning-fast update tracking
        self.pending_updates = {}  # {ch: (pos, timestamp)} - only keep latest position per knob
        self.last_display_update = 0.0
        self.min_update_interval = 0.05  # 50ms minimum between display updates for responsiveness
        self.display_busy = False  # track if display update is in progress
        
        # track last-main view to avoid redundant blits
        self.last_main_positions = {}
        self.running = False

        # Display worker queue and thread (drop-old behaviour)
        # _display_queue holds tuples (tag, PIL.Image, rotate, mode)
        self._display_queue = []
        self._display_queue_lock = threading.Lock()
        self._display_thread = threading.Thread(target=self._display_worker, name="picker-display-worker", daemon=True)
        self._display_thread_stop = False
        # Executor for per-blit worker so we can apply a timeout
        self._blit_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        # When a blit times out, disable further attempts until this timestamp
        self._display_disabled_until = 0.0
        # Save init params to allow re-init attempts later if desired
        self._spi_device = spi_device
        self._force_simulation = force_simulation

        # Add startup protection - ignore changes for first few seconds
        self.startup_time = time.time()
        self.startup_grace_period = 1.0  # seconds (reduced for testing)

        # Initialize display with proper SPI device
        logger.info(f"Initializing display on SPI device {spi_device} (rotate={rotate})")
        self.rotate = rotate
        display_success = display_init(spi_device=spi_device, force_simulation=force_simulation, rotate=rotate)
        if not display_success:
            logger.warning("Display initialization failed - continuing in simulation mode")
        else:
            # If the driver reports an actual size, use it as the canonical display_size
            real_size = get_display_size()
            if real_size:
                self.display_size = real_size
                if rotate in ('CW', 'CCW'):
                    self.effective_display_size = (self.display_size[1], self.display_size[0])
                else:
                    self.effective_display_size = self.display_size

        # Pre-render overlay images cache (per knob channel -> list of PIL Images)
        # This avoids costly text/font composition on each knob tick.
        self.overlay_cache = {}  # {ch: [PIL.Image, ...]}
        try:
            # Build cache for channels named "CH0".."CHn" found in texts
            for key, knob in self.texts.items():
                if not isinstance(key, str) or not key.startswith("CH"):
                    continue
                try:
                    ch_idx = int(key[2:])
                except Exception:
                    continue
                values = knob.get('values', [""] * 12) if knob else [""] * 12
                title = knob.get('title', key) if knob else key
                imgs = []
                for pos in range(len(values)):
                    try:
                        img = compose_overlay(title, values, max(0, min(len(values) - 1, pos)), full_screen=self.effective_display_size)
                    except Exception:
                        img = None
                    imgs.append(img)
                self.overlay_cache[ch_idx] = imgs
        except Exception:
            # If caching fails for any reason, leave overlay_cache empty and fall back
            # to on-demand composition in _process_knob_update
            logger.exception("Failed to build overlay cache; will compose overlays on-demand")

        # Start the display worker thread
        try:
            self._display_thread.start()
        except Exception:
            logger.exception("Failed to start display worker thread; display will be used synchronously")

    def _display_worker(self):
        """Worker thread that processes the latest display job and drops older ones.

        Queue entries are tuples: (tag, PIL.Image, rotate, mode)
        """
        import time as _time
        while not self._display_thread_stop:
            job = None
            try:
                with self._display_queue_lock:
                    if self._display_queue:
                        # keep only the newest job
                        job = self._display_queue[-1]
                        self._display_queue.clear()
            except Exception:
                job = None

            if job:
                # Skip attempts while display is marked disabled due to recent timeout
                if time.time() < self._display_disabled_until:
                    _time.sleep(0.02)
                    continue

                try:
                    tag, img, rotate, mode = job
                    # mark busy while performing blit
                    self.display_busy = True
                    # Submit blit to executor and wait with timeout
                    future = self._blit_executor.submit(blit, img, tag, rotate, mode)
                    try:
                        # Timeout controls how long we wait for hardware response
                        future.result(timeout=2.0)
                    except concurrent.futures.TimeoutError:
                        logger.error("Display worker: blit timed out; marking display disabled temporarily")
                        # Mark display disabled for a cooldown period to avoid repeated blocking
                        self._display_disabled_until = time.time() + 5.0
                    except Exception:
                        logger.exception("Display worker: blit raised")
                    finally:
                        # Do not attempt to cancel running thread (can't kill threads),
                        # but clear busy flag so UI is responsive. The hung blit thread
                        # will eventually finish or be left in the background.
                        self.display_busy = False
                        try:
                            self.last_display_update = time.time()
                        except Exception:
                            pass
                except Exception:
                    logger.exception("Display worker failed to schedule blit job")
            else:
                _time.sleep(0.005)

    def handle_knob_change(self, ch: int, pos: int):
        # Ignore knob changes during startup grace period
        if time.time() - self.startup_time < self.startup_grace_period:
            logger.debug(f"Ignoring startup knob change: CH{ch} -> position {pos}")
            return

        now = time.time()
        
        # Update activity timestamp for this knob to reset its overlay timeout
        self.last_activity_per_knob[ch] = now
        
        # Immediately process the update (enqueue latest job). The display worker
        # will drop intermediate frames if they arrive faster than the hardware.
        self._process_knob_update(ch, pos, now)

    def _process_knob_update(self, ch: int, pos: int, timestamp: float):
        """Process a knob update by rendering and blitting to display."""
        # Non-blocking: prepare image (prefer cache) and enqueue the blit job
        try:
            # Compose overlay for knob channel ch
            key = f"CH{ch}"
            knob = self.texts.get(key)
            title = knob.get("title", key) if knob else key
            values = knob.get("values", [""] * 12) if knob else [""] * 12

            # Invert the position for display so that low raw voltages appear
            # at the bottom of the menu and higher voltages move the selection
            # upward toward the top of the menu.
            display_pos = max(0, min(len(values) - 1, (len(values) - 1) - pos))

            logger.info(f"Knob change: CH{ch} -> position {pos} ('{title}'), display {display_pos}")

            img = None
            try:
                cached = self.overlay_cache.get(ch)
                if cached and 0 <= display_pos < len(cached):
                    img = cached[display_pos]
            except Exception:
                img = None

            if img is None:
                img = compose_overlay(title, values, display_pos, full_screen=self.effective_display_size)

            # Enqueue the latest blit job (drop-old semantics)
            with self._display_queue_lock:
                # Keep only newest job; drop existing ones
                self._display_queue.clear()
                self._display_queue.append((f"overlay_ch{ch}_pos{pos}", img, self.rotate, 'FAST'))

            # Mark overlay visible and update state; actual blit is handled by worker
            self.overlay_visible = True
            self.current_knob = (ch, pos)
            self.last_display_update = timestamp

        except Exception as e:
            logger.exception(f"Failed to enqueue knob update: {e}")

    def handle_go(self):
        logger.info("GO button pressed!")
        img = compose_message("GO!", full_screen=self.effective_display_size)
        blit(img, "go", rotate=self.rotate, mode='FAST')
        # GO overrides any overlay; clear overlay state
        self.overlay_visible = False
        self.current_knob = None

    def handle_reset(self):
        logger.info("RESET button pressed!")
        img = compose_message("RESETTING", full_screen=self.effective_display_size)
        blit(img, "reset", rotate=self.rotate, mode='FAST')
        # RESET overrides any overlay; clear overlay state
        self.overlay_visible = False
        self.current_knob = None

    def show_main(self):
        """Compose and blit the main idle screen immediately using current HW positions."""
        try:
            positions = self.hw.read_positions()
            # Build positions dict but invert indices for display to match overlay
            main_positions = {}
            for ch, (pos, changed) in positions.items():
                knob = self.texts.get(f"CH{ch}")
                values = knob.get('values', [""] * 12) if knob else [""] * 12
                display_pos = max(0, min(len(values) - 1, (len(values) - 1) - pos))
                main_positions[ch] = display_pos
            img = compose_main_screen(self.texts, main_positions, full_screen=self.effective_display_size)
            # Use auto mode for main screen to get proper grayscale rendering for images
            # Enqueue main screen as a display job (don't block)
            try:
                with self._display_queue_lock:
                    self._display_queue.clear()
                    self._display_queue.append(("main", img, self.rotate, 'auto'))
            except Exception:
                # Fallback to synchronous blit if queueing fails
                blit(img, "main", rotate=self.rotate, mode='auto')
            self.last_main_positions = main_positions
        except Exception:
            logger.exception("Failed to compose/show main screen")

    def loop_once(self):
        positions = self.hw.read_positions()
        buttons = self.hw.read_buttons()

        # Log hardware state for debugging
        active_positions = {ch: pos for ch, (pos, changed) in positions.items() if changed}
        active_buttons = {name: state for name, state in buttons.items() if state}

        if active_positions:
            logger.debug(f"Hardware positions: {active_positions}")
        if active_buttons:
            logger.debug(f"Hardware buttons: {active_buttons}")

        # Process knob changes - queue them for lightning-fast response
        for ch, (pos, changed) in positions.items():
            if changed:
                self.handle_knob_change(ch, pos)

        # Since we now process knob changes immediately in handle_knob_change(),
        # we no longer need separate pending update processing here.

        # buttons
        if buttons.get("GO"):
            self.handle_go()
        if buttons.get("RESET"):
            self.handle_reset()

        # overlay timeout: use per-knob activity so each knob keeps its own 2s window
        if self.overlay_visible and self.current_knob is not None:
            ch_now = self.current_knob[0]
            last = self.last_activity_per_knob.get(ch_now, 0)
            if (time.time() - last) > self.overlay_timeout:
                # Timeout: immediately return to the main screen without drawing
                # an intermediate blank overlay which causes a visual bar.
                logger.debug("Overlay timeout - returning to main screen (per-knob)")
                try:
                    # show_main composes and blits the main screen (uses high-quality mode)
                    self.show_main()
                except Exception:
                    # Fallback: if composing main fails, clear minimally
                    logger.exception("show_main failed during overlay timeout; falling back to clear")
                    img = compose_overlay("", [""] * 12, 0, full_screen=self.effective_display_size)
                    blit(img, "clear_overlay", rotate=self.rotate, mode='FAST')
                finally:
                    self.overlay_visible = False
                    self.current_knob = None

        if not self.overlay_visible:
            # build a simple positions dict mapping ch->pos
            # invert positions for display so main screen matches knob overlay
            main_positions = {}
            for ch, (pos, changed) in positions.items():
                knob = self.texts.get(f"CH{ch}")
                values = knob.get('values', [""] * 12) if knob else [""] * 12
                display_pos = max(0, min(len(values) - 1, (len(values) - 1) - pos))
                main_positions[ch] = display_pos
            # only redraw main screen if the selected positions changed
            if main_positions != self.last_main_positions:
                try:
                    img = compose_overlay("", [""] * 12, 0, full_screen=self.effective_display_size)
                    # If a more complete main screen composer exists, prefer it
                    try:
                        from picker.ui import compose_main_screen
                        main_img = compose_main_screen(self.texts, main_positions, full_screen=self.effective_display_size)
                        img = main_img
                    except Exception:
                        pass
                    blit(img, "main", rotate=self.rotate)
                    self.last_main_positions = main_positions
                except Exception:
                    logger.exception("Failed to draw main screen")

    def run(self, run_seconds: float = None):
        self.running = True
        start = time.time()
        try:
            while self.running:
                self.loop_once()
                time.sleep(self.hw.interval)
                if run_seconds and (time.time() - start) >= run_seconds:
                    break
        finally:
            self.running = False
            # Stop display worker thread and wait for it to finish
            try:
                self._display_thread_stop = True
                if self._display_thread and self._display_thread.is_alive():
                    self._display_thread.join(timeout=1.0)
            except Exception:
                pass


if __name__ == "__main__":
    # quick smoke main: runs with simulated HW
    from picker.hw import SimulatedMCP3008, Calibration
    sim = SimulatedMCP3008()
    # prepare simple calib map
    calib_map = {ch: Calibration() for ch in range(8)}
    hw = HW(adc_reader=sim, calib_map=calib_map)
    texts = load_texts()
    core = PickerCore(hw, texts, display_size=(800, 600))

    # demo: set some simulated channels over time
    sim.set_channel(0, 0)
    sim.set_channel(1, 512)
    sim.set_channel(2, 1023)
    core.loop_once()
    time.sleep(0.5)
    sim.set_channel(0, 700)
    core.loop_once()
    time.sleep(0.5)
    sim.set_channel(3, 900)  # GO
    core.loop_once()
    print('Demo finished')

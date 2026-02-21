"""Core state machine and event loop for the picker application.

This module is intentionally simple: it polls HW for knob changes and button presses,
invokes the UI composer, and routes output to the display adapter. It supports a
simulation mode when the HW instance is backed by `SimulatedMCP3008`.
"""
import time
import concurrent.futures
import threading
import logging
import subprocess
import base64
import io
import sys
from typing import Dict, Tuple

from picker.hw import HW
from picker.ui import compose_overlay, compose_message, compose_main_screen
from picker.drivers.display_fast import init as display_init, blit, partial_update, full_update, clear_display
from picker.drivers.display_fast import get_display_size
from picker.config import load_texts, DEFAULT_DISPLAY

logger = logging.getLogger(__name__)


class PickerCore:
    def __init__(self, hw: HW, texts: Dict = None, display_size: Tuple[int, int] = (1024, 600), spi_device=0, force_simulation=False, rotate: str = 'CW', generation_mode: str = 'txt2img', stream=False, stream_port=8088):
        self.hw = hw
        self.texts = texts or load_texts()
        self.display_size = display_size
        self.generation_mode = generation_mode
        # Initialize these early so they always exist (needed by capture_still.py status endpoint)
        self.last_image_source = None
        self.last_main_positions = {}
        self.last_interrogate = None
        self.last_gen_interrogate = None
        # If rotation will be applied, compose UI using the rotated dimensions
        if rotate in ('CW', 'CCW'):
            # swap width/height so composition matches final orientation
            self.effective_display_size = (display_size[1], display_size[0])
        else:
            self.effective_display_size = display_size

        self.overlay_visible = False
        self.overlay_timeout = 3.0  # seconds (default idle/menu clear timeout)
        # track last activity per knob channel so each knob keeps its own timeout
        self.last_activity_per_knob = {}
        # current knob being shown as an overlay: tuple (ch, pos) or None
        self.current_knob = None

        # Lightning-fast update tracking
        self.pending_updates = {}  # {ch: (pos, timestamp)} - only keep latest position per knob
        self.last_display_update = 0.0
        self.min_update_interval = 0.05  # 50ms minimum between display updates for responsiveness
        self.display_busy = False  # track if display update is in progress
        
        # Note: last_main_positions, last_interrogate, last_gen_interrogate are 
        # initialized early in __init__ so they always exist
        self.running = False
        self.stream_port = stream_port

        # Camera manager for img2img mode
        self.camera_manager = None
        if self.generation_mode == 'img2img' or stream:
            try:
                from picker.capture_still import CameraManager
                logger.info(f"Initializing camera (stream={stream}, port={stream_port})...")
                self.camera_manager = CameraManager(stream=stream, port=stream_port, core=self)
                if getattr(self.camera_manager, "stream_port", None):
                    self.stream_port = self.camera_manager.stream_port
            except Exception as e:
                logger.error(f"Failed to initialize camera: {e}")

        # Display worker queue and thread (drop-old behaviour)
        # _display_queue holds tuples (tag, PIL.Image, rotate, mode)
        self._display_queue = []
        self._display_queue_lock = threading.Lock()
        self._display_thread = threading.Thread(target=self._display_worker, name="picker-display-worker", daemon=True)
        self._display_thread_stop = False
        # Executor for per-blit worker so we can apply a timeout. Use two
        # workers so a single hung blit won't fully block future attempts.
        self._blit_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
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

        # Note: last_image_source is initialized early in __init__ so it always exists
        # When True, suppress automatic main-screen redraws until a
        # background generation finishes (or a timeout expires). This is
        # used so the temporary "GO" screen remains visible until the
        # newly-generated main content is available and blitted.
        self._suppress_main = False
        # Timestamp (epoch) until which suppression remains active.
        self._suppress_main_until = 0.0

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
                        # Schedule a background reinitialization attempt to recover the display
                        try:
                            threading.Thread(target=self._attempt_display_reinit, name="display-reinit", daemon=True).start()
                        except Exception:
                            logger.exception("Failed to start display reinit thread")
                    except Exception:
                        logger.exception("Display worker: blit raised")
                        # On persistent errors, also attempt a reinit in background
                        try:
                            threading.Thread(target=self._attempt_display_reinit, name="display-reinit", daemon=True).start()
                        except Exception:
                            logger.exception("Failed to start display reinit thread after exception")
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

    def _attempt_display_reinit(self):
        """Attempt to reinitialize the display in background.

        This is triggered after timeouts or persistent blit exceptions. The
        method will call the display adapter's reinit function and, on
        success, reset the disabled flag and replace the executor to avoid
        any stuck worker threads blocking future updates.
        """
        try:
            logger.info("Attempting background display reinitialization")
            from picker.drivers import display_fast
            ok = display_fast.reinit(spi_device=self._spi_device, force_simulation=self._force_simulation, rotate=self.rotate)
            if ok:
                logger.info("Display reinit successful - clearing disabled flag and refreshing executor")
                self._display_disabled_until = 0.0
                # Replace executor to avoid hung threads lingering
                try:
                    old = self._blit_executor
                    self._blit_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
                    try:
                        old.shutdown(wait=False)
                    except Exception:
                        logger.debug("Old blit executor shutdown failed (non-fatal)")
                except Exception:
                    logger.exception("Failed to replace blit executor after reinit")
            else:
                logger.warning("Display reinit attempt failed; will retry later if necessary")
        except Exception:
            logger.exception("Background display reinit failed")

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
        # Suppress automatic main redraws so the GO splash remains until the
        # generated main image is available. Clear any queued display jobs so
        # an older "main" job doesn't flash after the GO splash.
        try:
            with self._display_queue_lock:
                self._display_queue.clear()
        except Exception:
            logger.debug("Could not clear display queue before GO (non-fatal)")

        # Set suppression with a safety timeout to avoid permanent blocking
        # if generation fails. 20s should be more than enough for a typical
        # SD generation; adjust if necessary.
        self._suppress_main = True
        self._suppress_main_until = time.time() + 20.0

        # Immediately show GO message briefly (synchronous blit)
        img = compose_message("GO!", full_screen=self.effective_display_size)
        blit(img, "go", rotate=self.rotate, mode='FAST')

        # GO overrides any overlay; clear overlay state
        self.overlay_visible = False
        self.current_knob = None

        # Kick off background generation of an image for the main screen.
        # Build a CSV of knob-selected numeric positions (values are indices 0..n-1)
        try:
            # Read positions once at GO time and compute the display-position
            # mapping that should be shown on the main screen after the
            # generated image is ready. Capturing these now ensures the
            # final main screen (image + values) is consistent and updated
            # in a single blit rather than updating the image first and the
            # button values later.
            positions = self.hw.read_positions()
            # Build main_positions mapping (channel -> display_pos) using
            # the same inversion logic as `show_main` so on-screen indices
            # match what the user saw in overlays at GO time.
            main_positions = {}
            for ch, (pos, changed) in positions.items():
                knob = self.texts.get(f"CH{ch}")
                values = knob.get('values', [""] * 12) if knob else [""] * 12
                display_pos = max(0, min(len(values) - 1, (len(values) - 1) - pos))
                main_positions[ch] = display_pos

            # Use human-readable label values from texts (same ordering used
            # in the UI): channels [0,4,1,5,2,6]. Build the CSV from the
            # captured display positions so the prompt matches the shown
            # knob selections.
            knobs = [0, 4, 1, 5, 2, 6]
            labels = []
            for ch in knobs:
                display_pos = main_positions.get(ch, 0)
                knob = self.texts.get(f"CH{ch}")
                values = knob.get('values', [""] * 12) if knob else [""] * 12
                sel = values[display_pos] if display_pos < len(values) else ""
                sel = (sel or "").replace(',', ' ').strip()
                if sel:
                    labels.append(sel)
            knob_csv = ', '.join(labels)
        except Exception:
            knob_csv = ''

        # Compose prompt and start generation in a separate thread so we don't
        # block the main loop. The resulting image will be saved to the
        # Picker assets placeholder which `compose_main_screen` will load.
        try:
            import threading
            from picker import sd_config
            from picker import sd_client

            def _bg_generate():
                # Capture main_positions and knob_csv from the outer scope so
                # the background thread composes the final main screen using
                # the same knob selections that existed when GO was pressed.
                prompt = f"{sd_config.IMAGE_PROMPT_PREFIX}{knob_csv}{sd_config.IMAGE_PROMPT_SUFFIX}"
                init_image = None
                if self.generation_mode == 'img2img':
                    if self.camera_manager:
                        try:
                            logger.info("Capturing camera still for img2img...")
                            img = self.camera_manager.capture_still()
                            
                            # Convert PIL image to base64
                            buffered = io.BytesIO()
                            img.save(buffered, format="PNG")
                            init_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
                            logger.info(f"Image base64-encoded (length: {len(init_image)})")
                            
                            # Perform structured interrogation for demographics
                            try:
                                categories = {}
                                for ch_key in ["CH0", "CH1", "CH2", "CH4", "CH5", "CH6"]:
                                    knob_data = self.texts.get(ch_key)
                                    if knob_data and "title" in knob_data and "values" in knob_data:
                                        title = knob_data["title"]
                                        # Only include non-empty values
                                        valid_values = [v for v in knob_data["values"] if v and v.strip()]
                                        if valid_values:
                                            categories[title] = valid_values
                                
                                if categories:
                                    logger.info(f"Performing structured interrogation with {len(categories)} categories...")
                                    self.last_interrogate = sd_client.interrogate_structured(init_image, categories)
                                    logger.info("Structured interrogation complete")
                            except Exception as e:
                                logger.error(f"Structured interrogation failed: {e}")

                            # Also save to disk for debugging/reference as before
                            try:
                                from pathlib import Path
                                assets_dir = Path(__file__).parent / 'assets'
                                still_path = str(assets_dir / 'latest_still.png')
                                img.save(still_path)
                                logger.info(f"Saved latest camera still to {still_path}")
                            except Exception as e:
                                logger.warning(f"Failed to save latest_still.png: {e}")
                        except Exception as e:
                            logger.error(f"Failed to capture image for img2img: {e}, falling back to txt2img")
                    else:
                        logger.warning("Generation mode is img2img but camera_manager is None!")

                try:
                    sd_client.generate_image(prompt, output_path=sd_config.DEFAULT_OUTPUT_PATH, overrides={
                        'steps': sd_config.SD_STEPS,
                        'width': sd_config.SD_WIDTH,
                        'height': sd_config.SD_HEIGHT,
                        'cfg_scale': sd_config.SD_CFG_SCALE,
                        'sampler_name': sd_config.SD_SAMPLER_NAME,
                        'denoising_strength': sd_config.SD_DENOISING_STRENGTH,
                        'n_iter': sd_config.SD_N_ITER,
                        'batch_size': sd_config.SD_BATCH_SIZE,
                    }, mode=self.generation_mode, init_image=init_image)

                    # Interrogate generated image to get general tags
                    try:
                        # Construct categories if they were built earlier, otherwise just interrogation
                        # We use the same categories as the still image as requested
                        interrogation_categories = {}
                        for ch_key in ["CH0", "CH1", "CH2", "CH4", "CH5", "CH6"]:
                            knob_data = self.texts.get(ch_key)
                            if knob_data and "title" in knob_data and "values" in knob_data:
                                title = knob_data["title"]
                                valid_values = [v for v in knob_data["values"] if v and v.strip()]
                                if valid_values:
                                    interrogation_categories[title] = valid_values

                        with open(sd_config.DEFAULT_OUTPUT_PATH, "rb") as f:
                            gen_image_b64 = base64.b64encode(f.read()).decode('utf-8')
                        
                        logger.info("Interrogating generated image...")
                        self.last_gen_interrogate = sd_client.interrogate_structured(gen_image_b64, interrogation_categories)
                    except Exception as e:
                        logger.error(f"Interrogation of generated image failed: {e}")

                    # After generation, set the last_image_source to the prompt
                    # (or a concise knob CSV) so the UI annotation will match the
                    # image that was generated. Then request immediate main
                    # screen redraw using that fixed source text.
                    try:
                        # store the exact CSV (or prompt) that was used
                        try:
                            # prefer a short knob csv string
                            self.last_image_source = knob_csv
                        except Exception:
                            self.last_image_source = prompt

                        # Compose the final main screen using the latest knob
                        # positions available at compose-time so the bottom
                        # knob values reflect what the user currently has set.
                        # The top annotation (image_source_text) remains the
                        # GO-time prompt so it accurately describes the image
                        # that was generated.
                        try:
                            # Read fresh positions now that generation finished
                            latest_positions_raw = self.hw.read_positions()
                            latest_positions = {}
                            for ch, (pos, changed) in latest_positions_raw.items():
                                knob = self.texts.get(f"CH{ch}")
                                values = knob.get('values', [""] * 12) if knob else [""] * 12
                                display_pos = max(0, min(len(values) - 1, (len(values) - 1) - pos))
                                latest_positions[ch] = display_pos

                            img = compose_main_screen(self.texts, latest_positions, full_screen=self.effective_display_size, image_source_text=self.last_image_source)
                            blit(img, "main", rotate=self.rotate, mode='auto')
                            # Record that the last shown main positions now
                            # match the latest positions so the main loop won't
                            # perform a subsequent redundant refresh.
                            try:
                                self.last_main_positions = dict(latest_positions)
                            except Exception:
                                self.last_main_positions = latest_positions
                        except Exception:
                            logger.exception("Failed to compose/blit generated main screen")
                    finally:
                        # Generation finished (success or not) - allow main redraws
                        try:
                            self._suppress_main = False
                            self._suppress_main_until = 0.0
                        except Exception:
                            pass
                except Exception:
                    logger.exception("Background SD image generation failed")
                    # Ensure we don't permanently suppress main screen if
                    # background generation failed early.
                    try:
                        self._suppress_main = False
                        self._suppress_main_until = 0.0
                    except Exception:
                        pass

            t = threading.Thread(target=_bg_generate, name="sd-generate", daemon=True)
            t.start()
        except Exception:
            logger.exception("Failed to start background SD generation thread")

    def handle_reset(self):
        logger.info("RESET button pressed!")
        img = compose_message("RESETTING", full_screen=self.effective_display_size)
        blit(img, "reset", rotate=self.rotate, mode='FAST')
        # RESET overrides any overlay; clear overlay state
        self.overlay_visible = False
        self.current_knob = None
        # Perform a rock-solid display reinitialization and full refresh.
        try:
            logger.info("RESET requested: attempting synchronous display reinitialization")
            from picker.drivers import display_fast

            ok = display_fast.reinit(spi_device=self._spi_device, force_simulation=self._force_simulation, rotate=self.rotate)
            if ok:
                logger.info("Display reinit successful (RESET) - refreshing blit executor and performing full refresh")
                # Clear any disabled flag and replace the potentially-hung executor
                try:
                    self._display_disabled_until = 0.0
                except Exception:
                    pass

                try:
                    old = self._blit_executor
                    self._blit_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
                    try:
                        old.shutdown(wait=False)
                    except Exception:
                        logger.debug("Old blit executor shutdown during RESET failed (non-fatal)")
                except Exception:
                    logger.exception("Failed to replace blit executor after RESET")

                # Compose the main screen synchronously and request a full-mode blit
                try:
                    try:
                        positions = self.hw.read_positions()
                        main_positions = {}
                        for ch, (pos, changed) in positions.items():
                            knob = self.texts.get(f"CH{ch}")
                            values = knob.get('values', [""] * 12) if knob else [""] * 12
                            display_pos = max(0, min(len(values) - 1, (len(values) - 1) - pos))
                            main_positions[ch] = display_pos
                        img = compose_main_screen(self.texts, main_positions, full_screen=self.effective_display_size, image_source_text=self.last_image_source)
                    except Exception:
                        # Fallback to a simple composed overlay if main composer fails
                        logger.exception("Failed to compose main screen for RESET full refresh; using fallback overlay")
                        img = compose_overlay("", [""] * 12, 0, full_screen=self.effective_display_size)

                    # Use executor to run blit with a timeout so a hung driver doesn't block
                    try:
                        fut = self._blit_executor.submit(blit, img, "reset_full_refresh", self.rotate, 'full')
                        fut.result(timeout=6.0)
                        logger.info("RESET full refresh completed")
                        # Record that the last shown main positions now match the
                        # positions we used to compose the image so the main loop
                        # won't perform an immediate redundant redraw.
                        try:
                            self.last_main_positions = dict(main_positions)
                        except Exception:
                            self.last_main_positions = main_positions
                    except concurrent.futures.TimeoutError:
                        logger.error("RESET full refresh blit timed out")
                        # Try driver-level full_update as a fallback
                        try:
                            if display_fast.full_update():
                                try:
                                    self.last_main_positions = dict(main_positions)
                                except Exception:
                                    self.last_main_positions = main_positions
                        except Exception:
                            logger.exception("Driver-level full_update also failed during RESET")
                    except Exception:
                        logger.exception("RESET full refresh blit failed")
                except Exception:
                    logger.exception("RESET: failed to perform full refresh")
            else:
                logger.warning("Display reinit returned False during RESET; display may remain unavailable")
        except Exception:
            logger.exception("RESET: unexpected error during display reinitialization")

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
            img = compose_main_screen(self.texts, main_positions, full_screen=self.effective_display_size, image_source_text=self.last_image_source)
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
            # If suppression is active (e.g. we've just shown GO and are
            # waiting for generated content), skip automatic main redraws
            # until suppression is cleared or the safety timeout expires.
            if self._suppress_main:
                if time.time() > self._suppress_main_until:
                    # safety timeout expired - clear suppression so UI can
                    # return to showing the last known main screen.
                    logger.debug("GO suppression timed out; allowing main redraws")
                    self._suppress_main = False
                    self._suppress_main_until = 0.0
                else:
                    # Suppressed - do not redraw main now
                    return
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
                        main_img = compose_main_screen(self.texts, main_positions, full_screen=self.effective_display_size, image_source_text=self.last_image_source)
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
            # Stop camera if active
            if self.camera_manager:
                try:
                    logger.info("Stopping camera...")
                    self.camera_manager.stop()
                except Exception as e:
                    logger.warning(f"Error stopping camera: {e}")

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

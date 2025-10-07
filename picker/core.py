"""Core state machine and event loop for the picker application.

This module is intentionally simple: it polls HW for knob changes and button presses,
invokes the UI composer, and routes output to the display adapter. It supports a
simulation mode when the HW instance is backed by `SimulatedMCP3008`.
"""
import time
import threading
import logging
from typing import Dict, Tuple

from picker.hw import HW
from picker.ui import compose_overlay, compose_message, compose_main_screen
from picker.drivers.display_fast import init as display_init, blit, partial_update, full_update, clear_display
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
        self.overlay_timeout = 2.0  # seconds
        self.last_activity = 0.0
        self.current_knob = None
        # track last-main view to avoid redundant blits
        self.last_main_positions = {}
        self.running = False
        
        # Initialize display with proper SPI device
        logger.info(f"Initializing display on SPI device {spi_device} (rotate={rotate})")
        self.rotate = rotate
        display_success = display_init(spi_device=spi_device, force_simulation=force_simulation, rotate=rotate)
        if not display_success:
            logger.warning("Display initialization failed - continuing in simulation mode")

    def handle_knob_change(self, ch: int, pos: int):
        # Compose overlay for knob channel ch
        key = f"CH{ch}"
        knob = self.texts.get(key)
        title = knob.get("title", key) if knob else key
        values = knob.get("values", [""] * 12) if knob else [""] * 12
        
        logger.info(f"Knob change: CH{ch} -> position {pos} ('{title}')")
        img = compose_overlay(title, values, pos, full_screen=self.effective_display_size)
        blit(img, f"overlay_ch{ch}_pos{pos}", rotate=self.rotate)
        self.overlay_visible = True
        self.last_activity = time.time()
        self.current_knob = (ch, pos)

    def handle_go(self):
        logger.info("GO button pressed!")
        img = compose_message("GO!", full_screen=self.effective_display_size)
        blit(img, "go", rotate=self.rotate)
        self.overlay_visible = False
        self.last_activity = time.time()

    def handle_reset(self):
        logger.info("RESET button pressed!")
        img = compose_message("RESETTING", full_screen=self.effective_display_size)
        blit(img, "reset", rotate=self.rotate)
        self.overlay_visible = False
        self.last_activity = time.time()

    def show_main(self):
        """Compose and blit the main idle screen immediately using current HW positions."""
        try:
            positions = self.hw.read_positions()
            main_positions = {ch: pos for ch, (pos, changed) in positions.items()}
            img = compose_main_screen(self.texts, main_positions, full_screen=self.effective_display_size)
            blit(img, "main", rotate=self.rotate)
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

        # knobs: positions is dict {ch: (pos, changed)}
        for ch, (pos, changed) in positions.items():
            if changed:
                self.handle_knob_change(ch, pos)

        # buttons
        if buttons.get("GO"):
            self.handle_go()
        if buttons.get("RESET"):
            self.handle_reset()

        # overlay timeout
        if self.overlay_visible and (time.time() - self.last_activity) > self.overlay_timeout:
            # clear overlay by drawing a blank frame
            logger.debug("Clearing overlay due to timeout")
            img = compose_overlay("", [""] * 12, 0, full_screen=self.effective_display_size)
            blit(img, "clear_overlay", rotate=self.rotate)
            self.overlay_visible = False
            # after clearing overlay, draw main idle screen
        if not self.overlay_visible:
            # build a simple positions dict mapping ch->pos
            main_positions = {ch: pos for ch, (pos, changed) in positions.items()}
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

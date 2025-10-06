"""Core state machine and event loop for the picker application.

This module is intentionally simple: it polls HW for knob changes and button presses,
invokes the UI composer, and routes output to the display adapter. It supports a
simulation mode when the HW instance is backed by `SimulatedMCP3008`.
"""
import time
import threading
from typing import Dict, Tuple

from picker.hw import HW
from picker.ui import compose_overlay, compose_message
from picker.drivers.display_fast import init as display_init, blit, partial_update, full_update
from picker.config import load_texts, DEFAULT_DISPLAY


class PickerCore:
    def __init__(self, hw: HW, texts: Dict = None, display_size: Tuple[int, int] = (1024, 600)):
        self.hw = hw
        self.texts = texts or load_texts()
        self.display_size = display_size
        self.overlay_visible = False
        self.overlay_timeout = 2.0  # seconds
        self.last_activity = 0.0
        self.current_knob = None
        self.running = False
        display_init()

    def handle_knob_change(self, ch: int, pos: int):
        # Compose overlay for knob channel ch
        key = f"CH{ch}"
        knob = self.texts.get(key)
        title = knob.get("title", key) if knob else key
        values = knob.get("values", [""] * 12) if knob else [""] * 12
        img = compose_overlay(title, values, pos, full_screen=self.display_size)
        blit(img, f"overlay_ch{ch}_pos{pos}")
        self.overlay_visible = True
        self.last_activity = time.time()
        self.current_knob = (ch, pos)

    def handle_go(self):
        img = compose_message("GO!", full_screen=self.display_size)
        blit(img, "go")
        self.overlay_visible = False
        self.last_activity = time.time()

    def handle_reset(self):
        img = compose_message("RESETTING", full_screen=self.display_size)
        blit(img, "reset")
        self.overlay_visible = False
        self.last_activity = time.time()

    def loop_once(self):
        positions = self.hw.read_positions()
        buttons = self.hw.read_buttons()

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
            img = compose_overlay("", [""] * 12, 0, full_screen=self.display_size)
            blit(img, "clear_overlay")
            self.overlay_visible = False

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

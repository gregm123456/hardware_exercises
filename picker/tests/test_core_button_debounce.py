"""Tests for PickerCore button edge-detection (debounce) in loop_once.

Without this fix, handle_go / handle_reset fired on every loop iteration
while a button was held (120 Hz), which:
  1. Cleared the display queue each iteration, preventing knob overlays.
  2. Spawned multiple background SD generation threads per press.

The fix adds rising-edge detection via _prev_buttons so each action fires
exactly once per press (False → True transition).
"""
import types
from unittest.mock import MagicMock, patch, call

import pytest

from picker.hw import SimulatedMCP3008, HW, Calibration
from picker.config import load_texts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_core_with_mocked_display():
    """Build a PickerCore backed by simulated hardware and a no-op display."""
    sim_adc = SimulatedMCP3008()
    calib_map = {ch: Calibration() for ch in range(8)}
    hw = HW(adc_reader=sim_adc, calib_map=calib_map)
    texts = load_texts()

    with patch("picker.core.display_init", return_value=True), \
         patch("picker.core.blit"), \
         patch("picker.core.clear_display"), \
         patch("picker.core.get_display_size", return_value=None), \
         patch("picker.core.compose_overlay", return_value=MagicMock()), \
         patch("picker.core.compose_main_screen", return_value=MagicMock()), \
         patch("picker.core.compose_message", return_value=MagicMock()):
        from picker.core import PickerCore
        core = PickerCore(
            hw=hw,
            texts=texts,
            display_size=(1024, 600),
            force_simulation=True,
        )

    # Stop the display worker thread to avoid interference
    core._display_thread_stop = True

    return core, sim_adc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestButtonEdgeDetection:
    """handle_go / handle_reset must fire only on the rising edge."""

    def test_go_fires_once_on_press(self):
        """Pressing GO for multiple loop iterations calls handle_go exactly once."""
        core, sim_adc = _make_core_with_mocked_display()
        core.handle_go = MagicMock()
        core.handle_reset = MagicMock()

        # Simulate GO held for 5 iterations
        sim_adc.set_channel(3, 1023)  # GO channel high
        with patch("picker.core.blit"), \
             patch("picker.core.compose_overlay", return_value=MagicMock()), \
             patch("picker.core.compose_main_screen", return_value=MagicMock()):
            for _ in range(5):
                core.loop_once()

        # handle_go must be called exactly once (on the False→True edge)
        core.handle_go.assert_called_once()
        core.handle_reset.assert_not_called()

    def test_reset_fires_once_on_press(self):
        """Pressing RESET for multiple iterations calls handle_reset exactly once."""
        core, sim_adc = _make_core_with_mocked_display()
        core.handle_go = MagicMock()
        core.handle_reset = MagicMock()

        # Simulate RESET held for 5 iterations
        sim_adc.set_channel(7, 1023)  # RESET channel high
        with patch("picker.core.blit"), \
             patch("picker.core.compose_overlay", return_value=MagicMock()), \
             patch("picker.core.compose_main_screen", return_value=MagicMock()):
            for _ in range(5):
                core.loop_once()

        core.handle_reset.assert_called_once()
        core.handle_go.assert_not_called()

    def test_go_fires_again_after_release_and_repress(self):
        """After GO is released and pressed again, handle_go fires a second time."""
        core, sim_adc = _make_core_with_mocked_display()
        core.handle_go = MagicMock()

        with patch("picker.core.blit"), \
             patch("picker.core.compose_overlay", return_value=MagicMock()), \
             patch("picker.core.compose_main_screen", return_value=MagicMock()):
            # First press
            sim_adc.set_channel(3, 1023)
            core.loop_once()
            # Hold
            core.loop_once()
            # Release
            sim_adc.set_channel(3, 0)
            core.loop_once()
            # Second press
            sim_adc.set_channel(3, 1023)
            core.loop_once()
            # Hold again
            core.loop_once()

        assert core.handle_go.call_count == 2

    def test_no_action_when_button_not_pressed(self):
        """Neither action fires when both buttons remain unpressed."""
        core, sim_adc = _make_core_with_mocked_display()
        core.handle_go = MagicMock()
        core.handle_reset = MagicMock()

        with patch("picker.core.blit"), \
             patch("picker.core.compose_overlay", return_value=MagicMock()), \
             patch("picker.core.compose_main_screen", return_value=MagicMock()):
            for _ in range(10):
                core.loop_once()

        core.handle_go.assert_not_called()
        core.handle_reset.assert_not_called()

    def test_display_queue_not_cleared_by_held_button(self):
        """With edge detection, holding GO does not repeatedly clear the display queue.

        This is the core regression test: before the fix, handle_go cleared
        _display_queue on every iteration while GO was held, preventing knob
        overlays from ever being rendered.
        """
        core, sim_adc = _make_core_with_mocked_display()
        # Monkey-patch handle_go to track whether it's called multiple times
        call_count = [0]
        orig_handle_go = core.handle_go

        def counting_handle_go():
            call_count[0] += 1
            # Simulate what handle_go does: clear queue and set suppress
            with core._display_queue_lock:
                core._display_queue.clear()

        core.handle_go = counting_handle_go

        # Hold GO for 5 iterations
        sim_adc.set_channel(3, 1023)
        with patch("picker.core.blit"), \
             patch("picker.core.compose_overlay", return_value=MagicMock()), \
             patch("picker.core.compose_main_screen", return_value=MagicMock()):
            for _ in range(5):
                core.loop_once()

        # handle_go should have fired exactly once, not 5 times
        assert call_count[0] == 1

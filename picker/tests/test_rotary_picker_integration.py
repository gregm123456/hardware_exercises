"""Tests for the rotary-encoder + PickerCore integration in _run_rotary.

These tests validate the key integration logic introduced in _run_rotary:

* ch_by_menu_idx: channel mapping built from texts config.
* _sync_hw_from_rotary: rotary selections → simulated ADC positions.
* _do_display: TOP_MENU → compose_rotary_menu; SUBMENU → compose_overlay.
* _do_action: Go/Reset delegate to PickerCore.handle_go / handle_reset.
* Idle-to-main-screen timeout in TOP_MENU state.

All tests run with simulated hardware and a display-simulation PickerCore so
no real GPIO or SPI hardware is needed.
"""
import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

from picker.config import load_texts, load_menus
from picker.hw import HW, SimulatedMCP3008, Calibration
from picker.rotary_core import RotaryPickerCore, NavState
from picker.rotary_encoder import SimulatedRotaryEncoder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hw():
    """Return a (sim_adc, hw) pair backed by SimulatedMCP3008."""
    sim_adc = SimulatedMCP3008()
    calib_map = {ch: Calibration() for ch in range(8)}
    hw = HW(adc_reader=sim_adc, calib_map=calib_map)
    return sim_adc, hw


def _build_ch_by_menu_idx(texts):
    """Mirror the ch_by_menu_idx construction in _run_rotary."""
    ch_keys = sorted(
        (k for k in texts if isinstance(k, str) and k.startswith("CH")),
        key=lambda k: int(k[2:]),
    )
    return {i: int(k[2:]) for i, k in enumerate(ch_keys)}


def _sync_hw_from_rotary(rotary_core_ref, sim_adc, hw, ch_by_menu_idx):
    """Reproduce the _sync_hw_from_rotary helper from _run_rotary."""
    for menu_idx, item_idx in rotary_core_ref.selections.items():
        ch = ch_by_menu_idx.get(menu_idx)
        if ch is None:
            continue
        adc_pos = max(0, min(11, 11 - item_idx))
        raw = int((adc_pos + 0.5) * 1024 / 12)
        try:
            sim_adc.set_channel(ch, raw)
        except Exception:
            pass
        mapper = hw.mappers.get(ch)
        if mapper:
            mapper.state.last_pos = adc_pos
            mapper.state.last_raw = raw
            mapper.state.stable_count = 0


# ---------------------------------------------------------------------------
# ch_by_menu_idx construction
# ---------------------------------------------------------------------------

class TestChByMenuIdx:
    def test_maps_all_six_channels(self):
        texts = load_texts()
        mapping = _build_ch_by_menu_idx(texts)
        # sample_texts.json has CH0,CH1,CH2,CH4,CH5,CH6 → 6 menus
        assert len(mapping) == 6

    def test_channel_order_matches_sorted_ch_keys(self):
        texts = load_texts()
        mapping = _build_ch_by_menu_idx(texts)
        # CH0 < CH1 < CH2 < CH4 < CH5 < CH6 after numeric sort
        expected_channels = [0, 1, 2, 4, 5, 6]
        assert list(mapping.values()) == expected_channels

    def test_indices_are_zero_based_sequential(self):
        texts = load_texts()
        mapping = _build_ch_by_menu_idx(texts)
        assert list(mapping.keys()) == list(range(len(mapping)))


# ---------------------------------------------------------------------------
# _sync_hw_from_rotary
# ---------------------------------------------------------------------------

class TestSyncHwFromRotary:
    def _make_rotary_core_with_selections(self, selections: dict):
        """Build a RotaryPickerCore backed by the default sample menus."""
        menus = load_menus()
        rc = RotaryPickerCore(menus=menus, wrap=False)
        rc.selections.update(selections)
        return rc

    def test_default_selections_produce_adc_pos_11(self):
        """item_idx=0 (first item) → adc_pos = 11 - 0 = 11."""
        texts = load_texts()
        sim_adc, hw = _make_hw()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        menus = load_menus()
        rc = RotaryPickerCore(menus=menus, wrap=False)
        # all selections default to 0
        _sync_hw_from_rotary(rc, sim_adc, hw, ch_by_menu_idx)
        for menu_idx in range(len(menus)):
            ch = ch_by_menu_idx.get(menu_idx)
            if ch is None:
                continue
            mapper = hw.mappers[ch]
            assert mapper.state.last_pos == 11

    def test_selection_item_idx_translates_to_inverted_adc_pos(self):
        """item_idx=5 → adc_pos = 11 - 5 = 6."""
        texts = load_texts()
        sim_adc, hw = _make_hw()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        menus = load_menus()
        rc = RotaryPickerCore(menus=menus, wrap=False)
        rc.selections[0] = 5  # first menu, item index 5
        _sync_hw_from_rotary(rc, sim_adc, hw, ch_by_menu_idx)
        ch = ch_by_menu_idx[0]
        assert hw.mappers[ch].state.last_pos == 6

    def test_show_main_reflects_selection(self):
        """After _sync_hw_from_rotary, hw.read_positions gives the right display_pos."""
        texts = load_texts()
        sim_adc, hw = _make_hw()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        menus = load_menus()
        rc = RotaryPickerCore(menus=menus, wrap=False)
        # select item 3 in menu 0
        rc.selections[0] = 3
        _sync_hw_from_rotary(rc, sim_adc, hw, ch_by_menu_idx)
        ch = ch_by_menu_idx[0]
        positions = hw.read_positions()
        adc_pos, _ = positions[ch]
        display_pos = 11 - adc_pos  # same inversion PickerCore uses
        assert display_pos == 3

    def test_max_item_idx_clamped_to_11(self):
        """item_idx > 11 should clamp adc_pos to 0 (display_pos = 11)."""
        texts = load_texts()
        sim_adc, hw = _make_hw()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        menus = load_menus()
        rc = RotaryPickerCore(menus=menus, wrap=False)
        rc.selections[0] = 99  # out of range
        _sync_hw_from_rotary(rc, sim_adc, hw, ch_by_menu_idx)
        ch = ch_by_menu_idx[0]
        # adc_pos = max(0, min(11, 11-99)) = 0
        assert hw.mappers[ch].state.last_pos == 0

    def test_unknown_menu_idx_is_skipped(self):
        """A menu_idx not in ch_by_menu_idx should not raise."""
        texts = load_texts()
        sim_adc, hw = _make_hw()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        menus = load_menus()
        rc = RotaryPickerCore(menus=menus, wrap=False)
        rc.selections[99] = 2  # no channel for this index
        # Should not raise
        _sync_hw_from_rotary(rc, sim_adc, hw, ch_by_menu_idx)


# ---------------------------------------------------------------------------
# _do_display: TOP_MENU uses compose_rotary_menu
# ---------------------------------------------------------------------------

class TestDoDisplayTopMenu:
    def _make_do_display(self, menus, texts, ch_by_menu_idx, effective_size,
                         picker_core, rotary_core_holder, blit_calls, prev_menu_image):
        """Build an inline _do_display matching the partial-refresh pattern in _run_rotary."""
        import tempfile
        from picker.ui import compose_rotary_menu, compose_overlay

        def _do_display(title, items, selected_index):
            rc = rotary_core_holder[0]
            try:
                if rc is None or rc.state is NavState.TOP_MENU:
                    img = compose_rotary_menu(title, items, selected_index, full_screen=effective_size)
                    tmp_path = tempfile.gettempdir() + "/picker_rotary_menu_test.png"
                    img.save(tmp_path)
                    with picker_core._display_queue_lock:
                        picker_core._display_queue.clear()
                    if prev_menu_image[0] is not None:
                        blit_calls.append(('partial', prev_menu_image[0], img))
                    else:
                        blit_calls.append(('DU', None, img))
                    prev_menu_image[0] = tmp_path
                else:
                    menu_idx = rc._active_menu_idx
                    ch = ch_by_menu_idx.get(menu_idx)
                    _, submenu_values = rc.menus[menu_idx]
                    item_pos = selected_index - 1 if selected_index > 0 else rc.selections.get(menu_idx, 0)
                    item_pos = max(0, min(len(submenu_values) - 1, item_pos))
                    if ch is not None:
                        knob = texts.get(f"CH{ch}", {})
                        ch_title = knob.get('title', title)
                        ch_values = knob.get('values', submenu_values)
                        selected_label = submenu_values[item_pos] if item_pos < len(submenu_values) else ""
                        try:
                            display_idx = ch_values.index(selected_label)
                        except (ValueError, AttributeError):
                            display_idx = item_pos
                    else:
                        ch_title = title
                        ch_values = submenu_values
                        display_idx = item_pos
                    img = compose_overlay(ch_title, ch_values, display_idx, full_screen=effective_size)
                    with picker_core._display_queue_lock:
                        picker_core._display_queue.clear()
                        picker_core._display_queue.append(("rotary-sub", img, picker_core.rotate, 'FAST'))
                    prev_menu_image[0] = None  # screen changed; next TOP_MENU render uses full DU
            except Exception:
                pass

        return _do_display

    def test_top_menu_calls_blit_du_on_first_render(self):
        """On first TOP_MENU render _do_display calls blit with DU mode (no previous image)."""
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        effective_size = (800, 600)

        queue = []
        lock = threading.Lock()
        blit_calls = []
        prev_menu_image = [None]

        picker_core = MagicMock()
        picker_core._display_queue = queue
        picker_core._display_queue_lock = lock
        picker_core.rotate = None

        rotary_core_holder = [None]
        _do_display = self._make_do_display(
            menus, texts, ch_by_menu_idx, effective_size,
            picker_core, rotary_core_holder, blit_calls, prev_menu_image,
        )

        rotary_core = RotaryPickerCore(menus=menus, on_display=_do_display, wrap=False)
        rotary_core_holder[0] = rotary_core

        # Initial state is TOP_MENU; blit should have been called with DU mode
        assert blit_calls, "Expected blit to be called after init"
        mode, prev_path, img = blit_calls[-1]
        assert mode == 'DU'
        assert prev_path is None
        assert img.size == effective_size
        # Queue must be cleared (not used for TOP_MENU direct blit)
        assert not queue, "Queue should be empty after TOP_MENU direct blit"

    def test_top_menu_calls_blit_partial_on_subsequent_renders(self):
        """After the first render, TOP_MENU uses partial mode with the previous image path."""
        import os
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        effective_size = (800, 600)

        queue = []
        lock = threading.Lock()
        blit_calls = []
        prev_menu_image = [None]

        picker_core = MagicMock()
        picker_core._display_queue = queue
        picker_core._display_queue_lock = lock
        picker_core.rotate = None

        rotary_core_holder = [None]
        _do_display = self._make_do_display(
            menus, texts, ch_by_menu_idx, effective_size,
            picker_core, rotary_core_holder, blit_calls, prev_menu_image,
        )

        rotary_core = RotaryPickerCore(menus=menus, on_display=_do_display, wrap=False)
        rotary_core_holder[0] = rotary_core

        # Simulate a second rotation in TOP_MENU
        prev_count = len(blit_calls)
        rotary_core._refresh_display()

        # Second call should use partial mode with the path saved from first call
        assert len(blit_calls) > prev_count, "Expected another blit call after second render"
        mode, prev_path, img = blit_calls[-1]
        assert mode == 'partial'
        assert prev_path is not None
        assert os.path.exists(prev_path)
        assert img.size == effective_size

    def test_top_menu_prev_image_reset_on_submenu_entry(self):
        """After a SUBMENU display, prev_menu_image is reset so next TOP_MENU uses DU."""
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        effective_size = (800, 600)

        queue = []
        lock = threading.Lock()
        blit_calls = []
        prev_menu_image = [None]

        picker_core = MagicMock()
        picker_core._display_queue = queue
        picker_core._display_queue_lock = lock
        picker_core.rotate = None

        rotary_core_holder = [None]
        _do_display = self._make_do_display(
            menus, texts, ch_by_menu_idx, effective_size,
            picker_core, rotary_core_holder, blit_calls, prev_menu_image,
        )

        rotary_core = RotaryPickerCore(menus=menus, on_display=_do_display, wrap=False)
        rotary_core_holder[0] = rotary_core

        # After init (TOP_MENU), prev_menu_image should be set
        assert prev_menu_image[0] is not None

        # Enter submenu → should reset prev_menu_image
        rotary_core._cursor = 1  # first menu entry (Go is at 0, first category at 1)
        rotary_core.handle_button(True)
        rotary_core.handle_button(False)  # short press
        assert rotary_core.state is NavState.SUBMENU
        assert prev_menu_image[0] is None, "prev_menu_image must be None after SUBMENU display"

    def test_top_menu_uses_du_blit_after_returning_from_submenu(self):
        """Returning from a submenu must blit the main screen with DU mode (full refresh)."""
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        effective_size = (800, 600)

        queue = []
        lock = threading.Lock()
        blit_calls = []
        prev_menu_image = [None]

        picker_core = MagicMock()
        picker_core._display_queue = queue
        picker_core._display_queue_lock = lock
        picker_core.rotate = None

        rotary_core_holder = [None]
        _do_display = self._make_do_display(
            menus, texts, ch_by_menu_idx, effective_size,
            picker_core, rotary_core_holder, blit_calls, prev_menu_image,
        )

        rotary_core = RotaryPickerCore(menus=menus, on_display=_do_display, wrap=False)
        rotary_core_holder[0] = rotary_core

        # Enter submenu (cursor 1 = first category; Go is at 0)
        rotary_core._cursor = 1
        rotary_core.handle_button(True)
        rotary_core.handle_button(False)  # short press → enter submenu
        assert rotary_core.state is NavState.SUBMENU
        assert prev_menu_image[0] is None

        # Return from submenu via ↩ Return (cursor 0)
        rotary_core._cursor = 0
        rotary_core.handle_button(True)
        rotary_core.handle_button(False)  # short press → return to TOP_MENU
        assert rotary_core.state is NavState.TOP_MENU

        # The blit after returning must use DU (full refresh), not partial
        mode, prev_path, img = blit_calls[-1]
        assert mode == 'DU', "Returning from submenu must use DU mode (not partial)"
        assert prev_path is None
        assert img.size == effective_size


# ---------------------------------------------------------------------------
# _do_display: SUBMENU uses compose_overlay
# ---------------------------------------------------------------------------

class TestDoDisplaySubmenu:
    def test_submenu_enqueues_overlay_image(self):
        """In SUBMENU state, _do_display should enqueue a 'rotary-sub' job."""
        from picker.ui import compose_rotary_menu, compose_overlay
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        effective_size = (800, 600)

        queue = []
        lock = threading.Lock()

        picker_core = MagicMock()
        picker_core._display_queue = queue
        picker_core._display_queue_lock = lock
        picker_core.rotate = None

        rotary_core_holder = [None]

        def _do_display(title, items, selected_index):
            rc = rotary_core_holder[0]
            try:
                if rc is None or rc.state is NavState.TOP_MENU:
                    img = compose_rotary_menu(title, items, selected_index, full_screen=effective_size)
                    with picker_core._display_queue_lock:
                        picker_core._display_queue.clear()
                        picker_core._display_queue.append(("rotary-top", img, picker_core.rotate, 'DU'))
                else:
                    menu_idx = rc._active_menu_idx
                    ch = ch_by_menu_idx.get(menu_idx)
                    _, submenu_values = rc.menus[menu_idx]
                    item_pos = selected_index - 1 if selected_index > 0 else rc.selections.get(menu_idx, 0)
                    item_pos = max(0, min(len(submenu_values) - 1, item_pos))
                    if ch is not None:
                        knob = texts.get(f"CH{ch}", {})
                        ch_title = knob.get('title', title)
                        ch_values = knob.get('values', submenu_values)
                        selected_label = submenu_values[item_pos] if item_pos < len(submenu_values) else ""
                        try:
                            display_idx = ch_values.index(selected_label)
                        except (ValueError, AttributeError):
                            display_idx = item_pos
                    else:
                        ch_title = title
                        ch_values = submenu_values
                        display_idx = item_pos
                    img = compose_overlay(ch_title, ch_values, display_idx, full_screen=effective_size)
                    with picker_core._display_queue_lock:
                        picker_core._display_queue.clear()
                        picker_core._display_queue.append(("rotary-sub", img, picker_core.rotate, 'FAST'))
            except Exception:
                pass

        rotary_core = RotaryPickerCore(
            menus=menus,
            on_display=_do_display,
            wrap=False,
        )
        rotary_core_holder[0] = rotary_core

        # Enter submenu 0 (cursor must be at 1 — Go is at 0, first category at 1)
        rotary_core._cursor = 1
        rotary_core.handle_button(True)
        rotary_core.handle_button(False)  # short press
        assert rotary_core.state is NavState.SUBMENU

        # The last queued job should now be 'rotary-sub' (overlay)
        assert queue, "Expected a queued job after entering submenu"
        tag, img, _, mode = queue[-1]
        assert tag == "rotary-sub"
        assert mode == 'FAST'
        assert img.size == effective_size

    def test_submenu_cursor_on_return_highlights_saved_selection(self):
        """When cursor is on ↩ Return, overlay highlights the saved selection."""
        from picker.ui import compose_rotary_menu, compose_overlay
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        effective_size = (800, 600)
        queue = []
        lock = threading.Lock()
        picker_core = MagicMock()
        picker_core._display_queue = queue
        picker_core._display_queue_lock = lock
        picker_core.rotate = None

        overlay_calls = []
        rotary_core_holder = [None]

        def _do_display(title, items, selected_index):
            rc = rotary_core_holder[0]
            try:
                if rc is None or rc.state is NavState.TOP_MENU:
                    img = compose_rotary_menu(title, items, selected_index, full_screen=effective_size)
                    with lock:
                        queue.clear()
                        queue.append(("rotary-top", img, None, 'DU'))
                else:
                    menu_idx = rc._active_menu_idx
                    _, submenu_values = rc.menus[menu_idx]
                    if selected_index == 0:
                        item_pos = rc.selections.get(menu_idx, 0)
                    else:
                        item_pos = selected_index - 1
                    item_pos = max(0, min(len(submenu_values) - 1, item_pos))
                    overlay_calls.append(item_pos)
                    img = compose_overlay(title, submenu_values, item_pos, full_screen=effective_size)
                    with lock:
                        queue.clear()
                        queue.append(("rotary-sub", img, None, 'FAST'))
            except Exception:
                pass

        rotary_core = RotaryPickerCore(menus=menus, on_display=_do_display, wrap=False)
        rotary_core_holder[0] = rotary_core

        # Pre-save selection index 4 for menu 0
        rotary_core.selections[0] = 4
        # Enter submenu (cursor at 1 — Go is at 0, first category at 1)
        rotary_core._cursor = 1
        rotary_core.handle_button(True)
        rotary_core.handle_button(False)  # short press → enter submenu
        # Move cursor to Return (index 0)
        rotary_core._cursor = 0
        rotary_core._refresh_display()

        # When cursor is on Return, item_pos should be the saved selection (4)
        assert overlay_calls[-1] == 4


# ---------------------------------------------------------------------------
# _do_action delegates to PickerCore
# ---------------------------------------------------------------------------

class TestDoAction:
    def _run_action_test(self, action_name):
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        sim_adc, hw = _make_hw()

        picker_core = MagicMock()
        picker_core._display_queue = []
        picker_core._display_queue_lock = threading.Lock()

        rotary_core_holder = [None]

        def _do_display(title, items, selected_index):
            pass  # not testing display here

        def _sync(rc):
            _sync_hw_from_rotary(rc, sim_adc, hw, ch_by_menu_idx)

        def _do_action(action_name_inner):
            rc = rotary_core_holder[0]
            if rc is not None:
                _sync(rc)
            if action_name_inner == "Go":
                picker_core.handle_go()
            else:
                picker_core.handle_reset()

        rotary_core = RotaryPickerCore(
            menus=menus,
            on_display=_do_display,
            on_action=_do_action,
            wrap=False,
            long_press_seconds=0.05,  # short threshold for testing Reset
        )
        rotary_core_holder[0] = rotary_core

        # Navigate to Go (cursor 0) or trigger Reset via long press
        if action_name == "Go":
            rotary_core._cursor = 0  # "Go" is at index 0
            rotary_core.handle_button(True)
            rotary_core.handle_button(False)  # short press
        else:
            # Reset is triggered by a long press from any position
            rotary_core.handle_button(True)
            time.sleep(0.1)  # hold longer than threshold (0.05 s)
            rotary_core.handle_button(False)

        return picker_core

    def test_go_calls_handle_go(self):
        picker_core = self._run_action_test("Go")
        picker_core.handle_go.assert_called_once()
        picker_core.handle_reset.assert_not_called()

    def test_reset_calls_handle_reset(self):
        picker_core = self._run_action_test("Reset")
        picker_core.handle_reset.assert_called_once()
        picker_core.handle_go.assert_not_called()

    def test_go_syncs_hw_before_action(self):
        """_sync_hw_from_rotary is called before handle_go so PickerCore reads
        the correct knob positions when building the generation prompt."""
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        sim_adc, hw = _make_hw()

        synced_positions = {}

        picker_core = MagicMock()
        picker_core._display_queue = []
        picker_core._display_queue_lock = threading.Lock()

        def _fake_handle_go():
            # Capture mapper states at the time handle_go is called
            for ch in hw.KNOB_CHANNELS:
                synced_positions[ch] = hw.mappers[ch].state.last_pos

        picker_core.handle_go.side_effect = _fake_handle_go

        rotary_core_holder = [None]

        def _do_action(action_name_inner):
            rc = rotary_core_holder[0]
            if rc is not None:
                _sync_hw_from_rotary(rc, sim_adc, hw, ch_by_menu_idx)
            if action_name_inner == "Go":
                picker_core.handle_go()

        rotary_core = RotaryPickerCore(
            menus=menus,
            on_display=lambda *a: None,
            on_action=_do_action,
            wrap=False,
        )
        rotary_core_holder[0] = rotary_core

        # Set selection: menu 0 → item 2
        rotary_core.selections[0] = 2
        # "Go" is at cursor 0
        rotary_core._cursor = 0
        rotary_core.handle_button(True)
        rotary_core.handle_button(False)  # short press

        ch0 = ch_by_menu_idx[0]
        # display_pos = 2 → adc_pos = 11 - 2 = 9
        assert synced_positions[ch0] == 9


# ---------------------------------------------------------------------------
# Idle timeout: return to main screen after inactivity in TOP_MENU
# ---------------------------------------------------------------------------

class TestIdleTimeout:
    """The event loop returns to the main screen after idle_timeout seconds."""

    def test_show_main_called_after_idle(self):
        """Simulate the idle-timeout branch: after had_events=False for long
        enough in TOP_MENU, picker_core.show_main() should be called."""
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        sim_adc, hw = _make_hw()

        picker_core = MagicMock()
        rotary_core = RotaryPickerCore(menus=menus, on_display=lambda *a: None, wrap=False)
        assert rotary_core.state is NavState.TOP_MENU

        idle_timeout = 0.05  # very short for testing
        last_activity_time = time.time() - idle_timeout - 1.0
        showing_main = False

        # Replicate the event loop's idle check
        now = time.time()
        if (rotary_core.state is NavState.TOP_MENU
                and not showing_main
                and (now - last_activity_time) > idle_timeout):
            _sync_hw_from_rotary(rotary_core, sim_adc, hw, ch_by_menu_idx)
            picker_core.show_main()
            showing_main = True

        picker_core.show_main.assert_called_once()
        assert showing_main is True

    def test_no_show_main_while_in_submenu(self):
        """show_main is NOT called when rotary_core is in SUBMENU state."""
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        sim_adc, hw = _make_hw()

        picker_core = MagicMock()
        rotary_core = RotaryPickerCore(menus=menus, on_display=lambda *a: None, wrap=False)

        # Enter SUBMENU (cursor at 1 — Go is at 0, first category at 1)
        rotary_core._cursor = 1
        rotary_core.handle_button(True)
        rotary_core.handle_button(False)  # short press
        assert rotary_core.state is NavState.SUBMENU

        idle_timeout = 0.01
        last_activity_time = time.time() - idle_timeout - 1.0
        showing_main = False

        now = time.time()
        if (rotary_core.state is NavState.TOP_MENU
                and not showing_main
                and (now - last_activity_time) > idle_timeout):
            picker_core.show_main()
            showing_main = True

        # SUBMENU: show_main must NOT be called
        picker_core.show_main.assert_not_called()

    def test_no_show_main_if_already_showing(self):
        """show_main is NOT called again when showing_main is already True."""
        menus = load_menus()
        texts = load_texts()
        ch_by_menu_idx = _build_ch_by_menu_idx(texts)
        sim_adc, hw = _make_hw()

        picker_core = MagicMock()
        rotary_core = RotaryPickerCore(menus=menus, on_display=lambda *a: None, wrap=False)

        idle_timeout = 0.01
        last_activity_time = time.time() - idle_timeout - 1.0
        showing_main = True  # already showing main screen

        now = time.time()
        if (rotary_core.state is NavState.TOP_MENU
                and not showing_main
                and (now - last_activity_time) > idle_timeout):
            picker_core.show_main()

        picker_core.show_main.assert_not_called()

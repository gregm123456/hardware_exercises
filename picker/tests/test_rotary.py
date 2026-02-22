"""Unit tests for rotary encoder support.

Tests cover:
- SimulatedRotaryEncoder event injection and retrieval
- RotaryPickerCore navigation state machine (TOP_MENU / SUBMENU)
- load_menus() config parsing (legacy CH-key and new menus-list formats)
- compose_rotary_menu() UI rendering
"""
import json
import os
import tempfile

import pytest

from picker.rotary_encoder import SimulatedRotaryEncoder
from picker.rotary_core import RotaryPickerCore, NavState
from picker.config import load_menus
from picker.ui import compose_rotary_menu


# ---------------------------------------------------------------------------
# SimulatedRotaryEncoder
# ---------------------------------------------------------------------------

class TestSimulatedRotaryEncoder:
    def test_empty_queue_returns_none(self):
        enc = SimulatedRotaryEncoder()
        assert enc.get_event() is None

    def test_rotate_positive(self):
        enc = SimulatedRotaryEncoder()
        enc.simulate_rotate(3)
        events = [enc.get_event() for _ in range(3)]
        assert all(e == ("rotate", 1) for e in events)
        assert enc.get_event() is None

    def test_rotate_negative(self):
        enc = SimulatedRotaryEncoder()
        enc.simulate_rotate(-2)
        events = [enc.get_event() for _ in range(2)]
        assert all(e == ("rotate", -1) for e in events)
        assert enc.get_event() is None

    def test_rotate_zero_emits_nothing(self):
        enc = SimulatedRotaryEncoder()
        enc.simulate_rotate(0)
        assert enc.get_event() is None

    def test_button_press_and_release(self):
        enc = SimulatedRotaryEncoder()
        enc.simulate_button(True)
        enc.simulate_button(False)
        assert enc.get_event() == ("button", True)
        assert enc.get_event() == ("button", False)
        assert enc.get_event() is None

    def test_mixed_events_fifo(self):
        enc = SimulatedRotaryEncoder()
        enc.simulate_rotate(1)
        enc.simulate_button(True)
        enc.simulate_rotate(-1)
        assert enc.get_event() == ("rotate", 1)
        assert enc.get_event() == ("button", True)
        assert enc.get_event() == ("rotate", -1)
        assert enc.get_event() is None

    def test_cleanup_is_noop(self):
        enc = SimulatedRotaryEncoder()
        enc.cleanup()  # should not raise


# ---------------------------------------------------------------------------
# RotaryPickerCore
# ---------------------------------------------------------------------------

SAMPLE_MENUS = [
    ("Colour", ["Red", "Green", "Blue"]),
    ("Size", ["Small", "Medium", "Large"]),
]


def _make_core(**kwargs):
    """Helper: build a RotaryPickerCore with SAMPLE_MENUS and capture display calls."""
    display_calls = []
    action_calls = []

    def on_display(title, items, idx):
        display_calls.append((title, items, idx))

    def on_action(name):
        action_calls.append(name)

    core = RotaryPickerCore(SAMPLE_MENUS, on_display=on_display, on_action=on_action, **kwargs)
    return core, display_calls, action_calls


class TestRotaryPickerCoreInit:
    def test_starts_in_top_menu(self):
        core, _, _ = _make_core()
        assert core.state is NavState.TOP_MENU

    def test_initial_cursor_is_zero(self):
        core, _, _ = _make_core()
        assert core.cursor == 0

    def test_initial_display_called(self):
        core, calls, _ = _make_core()
        assert len(calls) >= 1
        title, items, idx = calls[-1]
        assert title == "Picker"
        assert "Go" in items
        assert "Colour" in items
        assert "Size" in items
        assert "Back" not in items
        assert "Reset" not in items
        assert idx == 0

    def test_empty_menus_raises(self):
        with pytest.raises(ValueError):
            RotaryPickerCore([])


class TestRotaryPickerCoreTopMenu:
    def test_rotate_cw_advances_cursor(self):
        core, calls, _ = _make_core()
        core.handle_rotate(+1)
        assert core.cursor == 1

    def test_rotate_ccw_does_not_go_below_zero_when_wrapping(self):
        core, _, _ = _make_core()
        core.handle_rotate(-1)
        # With wrap=True, rotating back from 0 wraps to last item
        n = len(SAMPLE_MENUS) + 1  # Go + menus
        assert core.cursor == n - 1

    def test_rotate_ccw_clamps_at_zero_when_no_wrap(self):
        core, _, _ = _make_core(wrap=False)
        core.handle_rotate(-1)
        assert core.cursor == 0

    def test_rotate_cw_wraps_at_end(self):
        core, _, _ = _make_core()
        n = len(SAMPLE_MENUS) + 1  # Go + menus
        for _ in range(n):
            core.handle_rotate(+1)
        assert core.cursor == 0

    def test_button_release_without_prior_press_is_ignored(self):
        core, calls, _ = _make_core()
        before = len(calls)
        core.handle_button(False)  # release with no matching press → no-op
        assert len(calls) == before  # no new display call
        assert core.state is NavState.TOP_MENU

    def test_short_press_on_go_triggers_action(self):
        core, _, action_calls = _make_core()
        # cursor is at 0 → "Go"
        core.handle_button(True)
        core.handle_button(False)
        assert "Go" in action_calls
        assert core.state is NavState.TOP_MENU

    def test_short_press_on_menu_enters_submenu(self):
        core, _, _ = _make_core()
        # "Colour" is at index 1 (Go is at 0)
        core._cursor = 1
        core.handle_button(True)
        core.handle_button(False)
        assert core.state is NavState.SUBMENU

    def test_long_press_triggers_reset(self):
        import time
        core, _, action_calls = _make_core(long_press_seconds=0.05)
        core.handle_button(True)
        time.sleep(0.1)  # hold longer than threshold
        core.handle_button(False)
        assert "Reset" in action_calls
        assert core.state is NavState.TOP_MENU

    def test_short_press_does_not_trigger_reset(self):
        core, _, action_calls = _make_core(long_press_seconds=10.0)
        core.handle_button(True)
        core.handle_button(False)  # much shorter than 10 s threshold
        assert "Reset" not in action_calls


class TestRotaryPickerCoreSubmenu:
    def test_submenu_items_start_with_return(self):
        core, calls, _ = _make_core()
        core._cursor = 1  # "Colour" is at index 1 (Go is at 0)
        core.handle_button(True)
        core.handle_button(False)  # short press → enter "Colour" submenu
        assert core.state is NavState.SUBMENU
        _, items, _ = calls[-1]
        assert items[0] == "↩ Return"
        assert any("Red" in item for item in items)
        assert any("Green" in item for item in items)
        assert any("Blue" in item for item in items)

    def test_submenu_ends_with_blank_when_not_selected(self):
        core, calls, _ = _make_core()
        core._cursor = 1  # "Colour"
        core.handle_button(True)
        core.handle_button(False)
        _, items, _ = calls[-1]
        # blank is last; with default selection (0, not blank), it is ""
        assert items[-1] == ""

    def test_submenu_ends_with_star_when_blank_is_selected(self):
        core, calls, _ = _make_core()
        _, values = core.menus[0]
        core.selections[0] = len(values)  # blank selected
        core._cursor = 1  # "Colour"
        core.handle_button(True)
        core.handle_button(False)
        _, items, _ = calls[-1]
        assert items[-1] == "* "

    def test_submenu_marks_saved_selection_with_star(self):
        core, calls, _ = _make_core()
        core.selections[0] = 1  # "Green" pre-selected
        core._cursor = 1  # "Colour"
        core.handle_button(True)
        core.handle_button(False)
        _, items, _ = calls[-1]
        # index 0 = Return, index 1 = Red, index 2 = * Green, ...
        assert items[2] == "* Green"
        assert items[1] == "Red"

    def test_submenu_cursor_starts_at_saved_selection(self):
        core, _, _ = _make_core()
        # Default selection for menu 0 is 0 → cursor should be 1 (0+1 for Return)
        core._cursor = 1  # "Colour"
        core.handle_button(True)
        core.handle_button(False)
        assert core.cursor == 1

    def test_rotate_in_submenu_moves_cursor(self):
        core, _, _ = _make_core()
        core._cursor = 1  # "Colour"
        core.handle_button(True)
        core.handle_button(False)
        core.handle_rotate(+1)
        assert core.cursor == 2

    def test_select_item_saves_selection_and_returns_to_top(self):
        core, _, _ = _make_core()
        core._cursor = 1   # "Colour"
        core.handle_button(True)
        core.handle_button(False)  # enter "Colour"
        core.handle_rotate(+1)     # move to index 2 ("Green")
        core.handle_button(True)
        core.handle_button(False)  # select "Green"
        assert core.state is NavState.TOP_MENU
        assert core.selections[0] == 1  # item_idx = cursor-1 = 2-1 = 1 → "Green"

    def test_cursor_resets_to_zero_after_submenu_select(self):
        core, _, _ = _make_core()
        core._cursor = 1   # "Colour"
        core.handle_button(True)
        core.handle_button(False)  # enter "Colour"
        core.handle_button(True)
        core.handle_button(False)  # select first item (cursor=1)
        assert core.state is NavState.TOP_MENU
        assert core.cursor == 0  # always back to "Go"

    def test_return_option_goes_back_without_changing_selection(self):
        core, _, _ = _make_core()
        core._cursor = 1   # "Colour"
        core.handle_button(True)
        core.handle_button(False)  # enter "Colour"
        # Move to Return (index 0)
        core._cursor = 0
        core.handle_button(True)
        core.handle_button(False)  # select Return
        assert core.state is NavState.TOP_MENU
        assert core.selections[0] == 0  # unchanged
        assert core.cursor == 0  # always back to "Go"

    def test_select_blank_saves_blank_selection(self):
        core, _, _ = _make_core()
        core._cursor = 1  # "Colour"
        core.handle_button(True)
        core.handle_button(False)  # enter "Colour"
        # Blank is at the last index: len(values)+1 (offset by Return)
        _, values = core.menus[0]
        core._cursor = len(values) + 1  # blank item
        core.handle_button(True)
        core.handle_button(False)
        assert core.state is NavState.TOP_MENU
        assert core.selections[0] == len(values)  # blank index

    def test_long_press_in_submenu_triggers_reset(self):
        import time
        core, _, action_calls = _make_core(long_press_seconds=0.05)
        core._cursor = 1  # "Colour"
        core.handle_button(True)
        core.handle_button(False)  # short press → enter submenu
        assert core.state is NavState.SUBMENU
        # Now long-press in submenu
        core.handle_button(True)
        time.sleep(0.1)
        core.handle_button(False)
        assert "Reset" in action_calls


class TestRotaryPickerCoreGetCurrentValues:
    def test_returns_dict_of_title_to_value(self):
        core, _, _ = _make_core()
        vals = core.get_current_values()
        assert "Colour" in vals
        assert "Size" in vals
        assert vals["Colour"] == "Red"   # default index 0
        assert vals["Size"] == "Small"   # default index 0

    def test_reflects_saved_selections(self):
        core, _, _ = _make_core()
        core.selections[1] = 2   # Size → "Large"
        vals = core.get_current_values()
        assert vals["Size"] == "Large"

    def test_blank_selection_returns_empty_string(self):
        core, _, _ = _make_core()
        _, values = core.menus[0]
        core.selections[0] = len(values)  # blank selection
        vals = core.get_current_values()
        assert vals["Colour"] == ""


# ---------------------------------------------------------------------------
# load_menus — config parsing
# ---------------------------------------------------------------------------

class TestLoadMenus:
    def test_loads_legacy_ch_format(self):
        menus = load_menus()   # uses sample_texts.json
        assert len(menus) >= 6
        titles = [t for t, _ in menus]
        assert "Sex/Gender" in titles

    def test_legacy_values_non_empty(self):
        menus = load_menus()
        for title, values in menus:
            assert len(values) > 0
            assert all(v.strip() for v in values)  # no blank strings

    def test_new_menus_list_format(self):
        data = {
            "menus": [
                {"title": "Fruit", "values": ["Apple", "Banana", "Cherry"]},
                {"title": "Veggie", "values": ["Carrot", "Pea"]},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            tmpname = f.name
        try:
            menus = load_menus(tmpname)
            assert len(menus) == 2
            assert menus[0] == ("Fruit", ["Apple", "Banana", "Cherry"])
            assert menus[1] == ("Veggie", ["Carrot", "Pea"])
        finally:
            os.unlink(tmpname)

    def test_new_format_filters_blank_values(self):
        data = {
            "menus": [
                {"title": "Test", "values": ["A", "", "B", "  "]},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            tmpname = f.name
        try:
            menus = load_menus(tmpname)
            assert menus[0][1] == ["A", "B"]
        finally:
            os.unlink(tmpname)

    def test_new_format_empty_menus_raises(self):
        data = {"menus": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            tmpname = f.name
        try:
            with pytest.raises(ValueError):
                load_menus(tmpname)
        finally:
            os.unlink(tmpname)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_menus("/nonexistent/path/config.json")

    def test_no_ch_keys_and_no_menus_key_raises(self):
        data = {"meta": {"version": "1.0"}}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(data, f)
            tmpname = f.name
        try:
            with pytest.raises(ValueError):
                load_menus(tmpname)
        finally:
            os.unlink(tmpname)


# ---------------------------------------------------------------------------
# compose_rotary_menu — UI rendering
# ---------------------------------------------------------------------------

class TestComposeRotaryMenu:
    def test_returns_correct_size(self):
        items = ["↩ Return", "Option A", "Option B", "Option C"]
        img = compose_rotary_menu("Test Menu", items, 1, full_screen=(400, 300))
        assert img.size == (400, 300)

    def test_selected_item_is_darker(self):
        """Selected row should have a dark pixel somewhere (inverted background)."""
        img_w, img_h = 400, 300
        items = ["Alpha", "Beta", "Gamma"]
        img = compose_rotary_menu("Test", items, 1, full_screen=(img_w, img_h))
        # Scan the left 12% of the image vertically (where the black selection
        # rectangle is drawn for the highlighted item).  Any pixel with value < 128
        # confirms the inversion rendering worked.
        scan_x_end = img_w // 8
        scan_y_margin = 5  # skip a few pixels at the very top/bottom
        pixels = [
            img.getpixel((x, y))
            for x in range(5, scan_x_end)
            for y in range(scan_y_margin, img_h - scan_y_margin)
        ]
        assert min(pixels) < 128, "No dark pixel found — selected item may not be highlighted"

    def test_many_items_renders_scroll_indicator(self):
        """With more items than visible rows, a scroll bar should be drawn."""
        img_w, img_h = 400, 300
        items = [f"Item {i}" for i in range(30)]
        img = compose_rotary_menu("Long List", items, 15, full_screen=(img_w, img_h))
        # The scroll indicator is drawn near the right edge (within the rightmost 5%
        # of the image width).  Its thumb rectangle uses fill=0, so at least one
        # dark pixel must appear in that strip.
        scroll_bar_x_start = int(img_w * 0.95)
        pixels = [
            img.getpixel((x, y))
            for x in range(scroll_bar_x_start, img_w)
            for y in range(0, img_h)
        ]
        assert min(pixels) < 200, "Scroll indicator not found in right edge"

    def test_variable_item_count(self):
        """compose_rotary_menu must not crash on lists of any length."""
        for n in (1, 2, 5, 12, 20, 50):
            items = [f"X{i}" for i in range(n)]
            img = compose_rotary_menu("Title", items, 0, full_screen=(800, 600))
            assert img.size == (800, 600)


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    # Run all test classes when invoked directly (without pytest).
    suites = [
        TestSimulatedRotaryEncoder,
        TestRotaryPickerCoreInit,
        TestRotaryPickerCoreTopMenu,
        TestRotaryPickerCoreSubmenu,
        TestRotaryPickerCoreGetCurrentValues,
        TestLoadMenus,
        TestComposeRotaryMenu,
    ]
    failed = 0
    for cls in suites:
        obj = cls()
        for name in dir(obj):
            if not name.startswith("test_"):
                continue
            method = getattr(obj, name)
            try:
                method()
                print(f"  OK  {cls.__name__}.{name}")
            except Exception as exc:
                print(f"FAIL  {cls.__name__}.{name}: {exc}")
                failed += 1
    if failed:
        print(f"\n{failed} test(s) FAILED")
        sys.exit(1)
    else:
        print("\nAll tests passed.")

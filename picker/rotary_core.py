"""Navigation state machine for single rotary-encoder + pushbutton picker.

This module replaces the six-knob / two-button MCP3008 input strategy with a
single rotary encoder knob that navigates a two-level hierarchical menu.

Top-level (TOP_MENU)
--------------------
The user rotates the knob to scroll through a list whose entries are:

    ["Go", menu_0_title, menu_1_title, ..., menu_N_title]

The cursor starts at 0 ("Go") so a simple press without turning fires Go.

Pressing the button:

* **short press** on **"Go"**       → fires the *Go* action
* **short press** on a **menu name** → enters that menu's sub-list (SUBMENU)
* **long press** (≥ ``long_press_seconds``) anywhere → fires the *Reset* action

The cursor is always reset to 0 ("Go") after returning from a sub-menu so the
user can immediately press Go or rotate to a category.

Sub-menu (SUBMENU)
------------------
The user rotates to scroll through:

    ["↩ Return", item_0, item_1, ..., item_K]

Pushing the button:

* **short press** on **"↩ Return"** → returns to TOP_MENU without changing the selection
* **short press** on any **item**   → saves that item as the current selection for this menu
                                      and returns to TOP_MENU
* **long press** anywhere           → fires the *Reset* action

The currently selected value for every menu is preserved in
:attr:`RotaryPickerCore.selections` (``{menu_index: item_index}``).

Display updates
---------------
:class:`RotaryPickerCore` calls two user-supplied callbacks on every
meaningful state change:

``on_display(title, items, selected_index)``
    Render the given list with the given item highlighted.  Called whenever
    the visible selection changes or the state transitions.

``on_action(action_name)``
    Called when the user triggers "Go" or "Reset".
    *action_name* is the string ``"Go"`` or ``"Reset"``.

Both callbacks are optional (default to no-ops).
"""
from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Special sentinel item names shown at the top level
_GO_LABEL = "Go"
_RESET_LABEL = "Reset"

# Sentinel item shown at the top of every sub-menu
_RETURN_LABEL = "↩ Return"


class NavState(Enum):
    TOP_MENU = auto()
    SUBMENU = auto()


class RotaryPickerCore:
    """Rotary-encoder navigation state machine for the picker application.

    Parameters
    ----------
    menus:
        Ordered list of ``(title, values)`` tuples, one entry per menu.
        *title* is a short display string; *values* is the list of
        selectable strings for that menu.  The list may contain any number
        of menus and each menu may have any number of values.
    on_display:
        Callback ``(title: str, items: List[str], selected_index: int) -> None``
        invoked whenever the visible selection changes and the display
        should be refreshed.
    on_action:
        Callback ``(action_name: str) -> None`` invoked when the user
        triggers "Go" (short press at top level) or "Reset" (long press
        from any state).
    wrap:
        When ``True`` (default), rotating past the end of a list wraps
        around to the other end.  Set to ``False`` for clamped behaviour.
    long_press_seconds:
        Duration in seconds a button must be held to trigger the "Reset"
        action.  Defaults to 3.0 seconds.
    """

    def __init__(
        self,
        menus: List[Tuple[str, List[str]]],
        on_display: Optional[Callable[[str, List[str], int], None]] = None,
        on_action: Optional[Callable[[str], None]] = None,
        wrap: bool = True,
        long_press_seconds: float = 3.0,
    ) -> None:
        if not menus:
            raise ValueError("menus must contain at least one entry")

        self.menus = menus
        self.wrap = wrap
        self._long_press_seconds = long_press_seconds

        self._on_display = on_display or (lambda title, items, idx: None)
        self._on_action = on_action or (lambda action: None)

        # Current selection index for each menu (defaults to 0)
        self.selections: Dict[int, int] = {i: 0 for i in range(len(menus))}

        # Navigation state
        self._state: NavState = NavState.TOP_MENU
        self._active_menu_idx: int = 0   # which menu is open in SUBMENU state
        self._cursor: int = 0             # index within the *currently shown* list

        # Button press tracking for long-press detection
        self._press_start: Optional[float] = None

        # Render initial display
        logger.info(f"RotaryPickerCore initialized with {len(menus)} menus")
        top_items = self._top_level_items()
        logger.info(f"Top-level items: {top_items}")
        self._refresh_display()

    # ------------------------------------------------------------------
    # Public event handlers
    # ------------------------------------------------------------------

    def handle_rotate(self, direction: int) -> None:
        """Handle a rotation event.

        Parameters
        ----------
        direction:
            ``+1`` for clockwise (next item), ``-1`` for counter-clockwise
            (previous item).
        """
        items = self._current_items()
        n = len(items)
        if n == 0:
            return

        new_cursor = self._cursor + direction
        if self.wrap:
            new_cursor = new_cursor % n
        else:
            new_cursor = max(0, min(n - 1, new_cursor))

        if new_cursor != self._cursor:
            self._cursor = new_cursor
            self._refresh_display()

    def handle_button(self, pressed: bool) -> None:
        """Handle a button event.

        The *press* transition (``pressed=True``) records the start time for
        long-press detection.  The *release* transition (``pressed=False``)
        dispatches the appropriate action:

        * If held for ≥ ``long_press_seconds`` → fires the *Reset* action.
        * Otherwise (short press) → navigates normally (Go at top level,
          enter sub-menu for a category, or select/return in a sub-menu).

        Parameters
        ----------
        pressed:
            ``True`` when the button is pushed down, ``False`` on release.
        """
        if pressed:
            self._press_start = time.time()
            return  # action deferred until release

        # Release event: determine press duration and dispatch.
        if self._press_start is None:
            return  # spurious release with no matching press

        duration = time.time() - self._press_start
        self._press_start = None

        if duration >= self._long_press_seconds:
            logger.info(f"Long press detected ({duration:.2f}s) — Action: Reset")
            try:
                self._on_action(_RESET_LABEL)
            except Exception:
                logger.exception("on_action(Reset) callback raised an exception")
        else:
            if self._state is NavState.TOP_MENU:
                self._handle_top_select()
            else:
                self._handle_submenu_select()

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> NavState:
        """Current navigation state (``TOP_MENU`` or ``SUBMENU``)."""
        return self._state

    @property
    def cursor(self) -> int:
        """Zero-based index of the currently highlighted item."""
        return self._cursor

    def current_display(self) -> Tuple[str, List[str], int]:
        """Return ``(title, items, cursor)`` for the currently visible list."""
        return self._current_title(), self._current_items(), self._cursor

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _top_level_items(self) -> List[str]:
        """Return the flat list shown at the top level.

        The list begins with "Go" so a press without any rotation immediately
        triggers image generation.  Category names follow, allowing the user
        to rotate to a category and press to enter its sub-menu.  "Reset" is
        no longer in this list — it is triggered by a long button press.
        """
        names = [title for title, _ in self.menus]
        return [_GO_LABEL] + names

    def _submenu_items(self, menu_idx: int) -> List[str]:
        """Return the items list for a sub-menu, prefixed with Return.

        The currently-saved selection is visually marked with ``* ``.
        A blank entry is appended as the last choice (no selection).
        """
        _, values = self.menus[menu_idx]
        saved = self.selections.get(menu_idx, 0)
        n = len(values)
        display_values = [
            f"* {v}" if i == saved else v
            for i, v in enumerate(values)
        ]
        # Mark the trailing blank item if it is the saved selection
        blank = "* " if saved == n else ""
        return [_RETURN_LABEL] + display_values + [blank]

    def _current_items(self) -> List[str]:
        if self._state is NavState.TOP_MENU:
            return self._top_level_items()
        return self._submenu_items(self._active_menu_idx)

    def _current_title(self) -> str:
        if self._state is NavState.TOP_MENU:
            return "Picker"
        title, _ = self.menus[self._active_menu_idx]
        return title

    def _refresh_display(self) -> None:
        title = self._current_title()
        items = self._current_items()
        logger.info(
            "→ Display refresh: state=%s title=%r cursor=%d/%d items=%r",
            self._state.name, title, self._cursor, len(items),
            items[:5] + (['...'] if len(items) > 5 else []),
        )
        try:
            self._on_display(title, items, self._cursor)
        except Exception:
            logger.exception("on_display callback raised an exception")

    def _handle_top_select(self) -> None:
        n_menus = len(self.menus)
        # Ordering: [Go, <menus...>]
        if self._cursor == 0:
            # "Go" selected (default position — press without rotating = Go)
            logger.info("Action: Go")
            try:
                self._on_action(_GO_LABEL)
            except Exception:
                logger.exception("on_action(Go) callback raised an exception")

        elif 1 <= self._cursor <= n_menus:
            # Enter the selected menu (cursor offset by 1 for the Go entry)
            self._active_menu_idx = self._cursor - 1
            self._state = NavState.SUBMENU
            # Start cursor at the item currently selected for this menu
            # (+1 because index 0 is "↩ Return")
            saved = self.selections.get(self._active_menu_idx, 0)
            self._cursor = saved + 1  # offset by the Return entry
            logger.debug(
                "Entering submenu %d (%r), cursor=%d",
                self._active_menu_idx,
                self.menus[self._active_menu_idx][0],
                self._cursor,
            )
            self._refresh_display()

    def _handle_submenu_select(self) -> None:
        if self._cursor == 0:
            # "↩ Return" — go back without changing selection
            logger.debug(
                "Return from submenu %d to TOP_MENU", self._active_menu_idx
            )
            self._state = NavState.TOP_MENU
            # Always reset to "Back" (index 0) so the user can immediately go back
            self._cursor = 0
            self._refresh_display()
        else:
            # An actual item was selected (cursor offset by 1 for Return)
            item_idx = self._cursor - 1
            self.selections[self._active_menu_idx] = item_idx
            title, values = self.menus[self._active_menu_idx]
            logger.info(
                "Selected %r → %r (index %d)",
                title,
                values[item_idx] if item_idx < len(values) else "",
                item_idx,
            )
            # Return to top level; reset cursor to "Back" (index 0)
            self._state = NavState.TOP_MENU
            self._cursor = 0
            self._refresh_display()

    def get_current_values(self) -> Dict[str, str]:
        """Return the current selected value for every menu.

        Returns
        -------
        dict
            Mapping of ``menu_title → selected_value_string``.  If no item
            has been explicitly selected for a menu, ``item_index=0`` is used.
            An index equal to ``len(values)`` represents the blank (no
            selection) choice and returns an empty string.
        """
        result: Dict[str, str] = {}
        for i, (title, values) in enumerate(self.menus):
            idx = self.selections.get(i, 0)
            # Allow idx == len(values) to represent the blank/no-selection choice
            idx = max(0, min(idx, len(values)))
            result[title] = values[idx] if idx < len(values) else ""
        return result

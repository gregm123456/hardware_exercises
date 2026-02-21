"""Navigation state machine for single rotary-encoder + pushbutton picker.

This module replaces the six-knob / two-button MCP3008 input strategy with a
single rotary encoder knob that navigates a two-level hierarchical menu:

Top-level (TOP_MENU)
--------------------
The user rotates the knob to scroll through a list whose entries are:

    [menu_0_title, menu_1_title, ..., menu_N_title, "Go", "Reset"]

Pushing the button:

* on a **menu name** → enters that menu's sub-list (SUBMENU state)
* on **"Go"**         → fires the *go* action and returns to TOP_MENU
* on **"Reset"**      → fires the *reset* action and returns to TOP_MENU

Sub-menu (SUBMENU)
------------------
The user rotates to scroll through:

    ["↩ Return", item_0, item_1, ..., item_K]

Pushing the button:

* on **"↩ Return"** → returns to TOP_MENU without changing the selection
* on any **item**   → saves that item as the current selection for this menu
                      and returns to TOP_MENU

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
    Called when the user selects "Go" or "Reset" at the top level.
    *action_name* is the string ``"Go"`` or ``"Reset"``.

Both callbacks are optional (default to no-ops).
"""
from __future__ import annotations

import logging
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
        selects "Go" or "Reset" at the top level.
    wrap:
        When ``True`` (default), rotating past the end of a list wraps
        around to the other end.  Set to ``False`` for clamped behaviour.
    """

    def __init__(
        self,
        menus: List[Tuple[str, List[str]]],
        on_display: Optional[Callable[[str, List[str], int], None]] = None,
        on_action: Optional[Callable[[str], None]] = None,
        wrap: bool = True,
    ) -> None:
        if not menus:
            raise ValueError("menus must contain at least one entry")

        self.menus = menus
        self.wrap = wrap

        self._on_display = on_display or (lambda title, items, idx: None)
        self._on_action = on_action or (lambda action: None)

        # Current selection index for each menu (defaults to 0)
        self.selections: Dict[int, int] = {i: 0 for i in range(len(menus))}

        # Navigation state
        self._state: NavState = NavState.TOP_MENU
        self._active_menu_idx: int = 0   # which menu is open in SUBMENU state
        self._cursor: int = 0             # index within the *currently shown* list

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

        Only the *press* transition (``pressed=True``) triggers navigation.
        The release event (``pressed=False``) is silently ignored so that
        navigation is not accidentally triggered twice.

        Parameters
        ----------
        pressed:
            ``True`` when the button is pushed down, ``False`` on release.
        """
        if not pressed:
            return  # act only on press, ignore release

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
        """Return the flat list shown at the top level."""
        names = [title for title, _ in self.menus]
        return names + [_GO_LABEL, _RESET_LABEL]

    def _submenu_items(self, menu_idx: int) -> List[str]:
        """Return the items list for a sub-menu, prefixed with Return."""
        _, values = self.menus[menu_idx]
        return [_RETURN_LABEL] + list(values)

    def _current_items(self) -> List[str]:
        if self._state is NavState.TOP_MENU:
            return self._top_level_items()
        return self._submenu_items(self._active_menu_idx)

    def _current_title(self) -> str:
        if self._state is NavState.TOP_MENU:
            return "Select Menu"
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
        items = self._top_level_items()
        n_menus = len(self.menus)

        if self._cursor < n_menus:
            # Enter the selected menu
            self._active_menu_idx = self._cursor
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

        elif self._cursor == n_menus:
            # "Go" selected
            logger.info("Action: Go")
            try:
                self._on_action(_GO_LABEL)
            except Exception:
                logger.exception("on_action(Go) callback raised an exception")

        elif self._cursor == n_menus + 1:
            # "Reset" selected
            logger.info("Action: Reset")
            try:
                self._on_action(_RESET_LABEL)
            except Exception:
                logger.exception("on_action(Reset) callback raised an exception")

    def _handle_submenu_select(self) -> None:
        if self._cursor == 0:
            # "↩ Return" — go back without changing selection
            logger.debug(
                "Return from submenu %d to TOP_MENU", self._active_menu_idx
            )
            self._state = NavState.TOP_MENU
            # Restore cursor to the menu that was just open
            self._cursor = self._active_menu_idx
            self._refresh_display()
        else:
            # An actual item was selected (cursor offset by 1 for Return)
            item_idx = self._cursor - 1
            self.selections[self._active_menu_idx] = item_idx
            title, values = self.menus[self._active_menu_idx]
            logger.info(
                "Selected %r → %r (index %d)",
                title,
                values[item_idx] if item_idx < len(values) else "?",
                item_idx,
            )
            # Return to top level, cursor stays on the menu that was just set
            self._state = NavState.TOP_MENU
            self._cursor = self._active_menu_idx
            self._refresh_display()

    def get_current_values(self) -> Dict[str, str]:
        """Return the current selected value for every menu.

        Returns
        -------
        dict
            Mapping of ``menu_title → selected_value_string``.  If no item
            has been explicitly selected for a menu, ``item_index=0`` is used.
        """
        result: Dict[str, str] = {}
        for i, (title, values) in enumerate(self.menus):
            idx = self.selections.get(i, 0)
            idx = max(0, min(idx, len(values) - 1))
            result[title] = values[idx] if values else ""
        return result

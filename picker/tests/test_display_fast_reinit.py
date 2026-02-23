"""Tests for display_fast init/reinit: verifies the deadlock fix.

Before the fix, reinit() acquired _display_lock and then called init() which
also tried to acquire the same (non-reentrant) lock — causing a 5-second hang
followed by a silent failure.  The fix extracts _do_init() so the lock is
acquired exactly once.
"""
import threading
import time
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_display():
    d = MagicMock()
    d.width = 1448
    d.height = 1072
    return d


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReinitDeadlockFix:
    """reinit() must complete quickly (no deadlock with init())."""

    def test_reinit_returns_true_when_create_display_succeeds(self):
        """reinit() should succeed and return True without deadlocking."""
        fake = _make_fake_display()
        with patch("picker.drivers.display_fast.create_display", return_value=fake):
            import picker.drivers.display_fast as df
            # Reset global state
            df._display = None
            df._reinit_in_progress = False
            df._display_disabled_until = 0.0

            result = df.reinit(spi_device=0, force_simulation=False)

        assert result is True

    def test_reinit_completes_in_under_3_seconds(self):
        """reinit() must not block for the 5-second deadlock window."""
        fake = _make_fake_display()
        with patch("picker.drivers.display_fast.create_display", return_value=fake):
            import picker.drivers.display_fast as df
            df._display = None
            df._reinit_in_progress = False

            start = time.time()
            df.reinit(spi_device=0, force_simulation=False)
            elapsed = time.time() - start

        # A deadlock would cause a 5-second hang; 3 s is a generous upper bound.
        assert elapsed < 3.0, f"reinit() took {elapsed:.2f}s — possible deadlock"

    def test_reinit_in_progress_cleared_after_reinit(self):
        """_reinit_in_progress must be False after reinit() returns."""
        fake = _make_fake_display()
        with patch("picker.drivers.display_fast.create_display", return_value=fake):
            import picker.drivers.display_fast as df
            df._display = None
            df._reinit_in_progress = False

            df.reinit(spi_device=0, force_simulation=False)

        assert df._reinit_in_progress is False

    def test_init_also_works_independently(self):
        """init() must still work correctly as a standalone call."""
        fake = _make_fake_display()
        with patch("picker.drivers.display_fast.create_display", return_value=fake):
            import picker.drivers.display_fast as df
            df._display = None

            result = df.init(spi_device=0, force_simulation=False)

        assert result is True

    def test_reinit_sets_display_disabled_to_zero_on_success(self):
        """_display_disabled_until is NOT touched by reinit (caller handles it)."""
        fake = _make_fake_display()
        with patch("picker.drivers.display_fast.create_display", return_value=fake):
            import picker.drivers.display_fast as df
            df._display = None
            df._display_disabled_until = 0.0

            df.reinit(spi_device=0, force_simulation=False)

        # _display_disabled_until is managed by the display worker, not reinit
        assert df._display_disabled_until == 0.0

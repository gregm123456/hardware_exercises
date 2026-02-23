"""Standalone display adapter for picker application.

This module provides a self-contained e-paper display interface without external dependencies.
Uses the enhanced epaper driver which can optionally leverage IT8951 when available.
"""
from pathlib import Path
from typing import Tuple
import logging

from PIL import Image
from .epaper_enhanced import create_display

logger = logging.getLogger(__name__)

OUT_DIR = Path("/tmp/picker_display")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Global display instance
_display = None
# Lock to serialize access to the display instance to avoid races between
# blit() calls and reinitialization/close operations. Use a simple Lock so
# long-running hardware ops block reinit until they finish. For interactive
# responsiveness, blit will try to acquire the lock with a short timeout and
# fail fast if a reinit/close is underway.
import threading
_display_lock = threading.Lock()
# Flag set while a reinitialization is intentionally in progress
_reinit_in_progress = False


def _do_init(spi_device=0, force_simulation=False):
    """Inner init logic — **must be called with _display_lock already held**.

    Closes any existing display, creates a fresh instance, and updates the
    global ``_display``.  Returns True on success, False otherwise.
    """
    global _display
    try:
        # Close the old instance first to release hardware resources.
        try:
            if _display:
                _display.close()
        except Exception:
            logger.debug("Existing display close during init failed; continuing")

        _display = create_display(
            spi_device=spi_device,
            vcom=-2.06,
            force_simulation=force_simulation,
            prefer_enhanced=True,
        )
        logger.info(f"Display initialized (SPI device {spi_device})")
        return True
    except Exception as e:
        logger.error(f"Display initialization failed: {e}")
        _display = None
        return False


def init(spi_device=0, force_simulation=False, rotate: str = None):
    """Initialize display adapter.
    
    Args:
        spi_device: SPI device number (0 for CE0, 1 for CE1)
        force_simulation: Force simulation mode for testing
    
    Returns:
        True if initialization successful
    """
    global _display_lock
    # Perform init under lock to avoid races with blit/close
    acquired = _display_lock.acquire(timeout=5.0)
    if not acquired:
        logger.error("Failed to acquire display lock for init")
        return False
    try:
        return _do_init(spi_device=spi_device, force_simulation=force_simulation)
    finally:
        _display_lock.release()


def reinit(spi_device=0, force_simulation=False, rotate: str = None):
    """Convenience wrapper to reinitialize the display from runtime.

    This will attempt to close any existing display and create a fresh one.
    Returns True on success, False otherwise.

    Previously this called ``init()`` while already holding ``_display_lock``,
    which caused a deadlock because ``init()`` also tries to acquire the same
    non-reentrant lock.  Now both functions share the internal ``_do_init()``
    helper so the lock is acquired exactly once.
    """
    global _reinit_in_progress, _display_lock
    # Mark reinit in progress so blit calls can fail fast
    _reinit_in_progress = True
    try:
        acquired = _display_lock.acquire(timeout=6.0)
        if not acquired:
            logger.error("Could not acquire display lock for reinit")
            return False
        try:
            return _do_init(spi_device=spi_device, force_simulation=force_simulation)
        finally:
            _display_lock.release()
    finally:
        _reinit_in_progress = False


def blit(full_bitmap: Image.Image, file_label: str = "frame", rotate: str = None, mode: str = 'auto', prev_image_path: str = None) -> Path:
    """Write a full-screen bitmap to the real display if available; otherwise save to /tmp.

    Hardware setup: epaper display is on CE0. Uses standalone e-paper driver for 
    optimal performance and reliability.
    
    Args:
        full_bitmap: Image to display
        file_label: Label for logging/debugging
        rotate: Rotation mode ('CW', 'CCW', 'flip', or None)
        mode: Display mode ('auto', 'DU', 'partial', etc.)
        prev_image_path: Path to previous image for partial refresh (enables true differential update)
    """
    global _display
    
    # Apply rotation if requested (rotate is one of 'CW','CCW','flip' or None)
    img_to_send = full_bitmap
    if rotate:
        try:
            if rotate == 'CW':
                img_to_send = full_bitmap.rotate(-90, expand=True)
            elif rotate == 'CCW':
                img_to_send = full_bitmap.rotate(90, expand=True)
            elif rotate == 'flip':
                img_to_send = full_bitmap.transpose(Image.FLIP_LEFT_RIGHT)
        except Exception:
            logger.exception('Rotation failed, proceeding without rotation')

    # Fast-fail if a reinit is currently in progress
    if _reinit_in_progress:
        logger.error("Display reinitialization in progress - blit aborted")
        return None

    # Try to acquire the display lock quickly so we don't block long-running
    # update threads (they may be stuck); if we can't get the lock we abort
    # this blit so higher-level logic can retry later.
    acquired = _display_lock.acquire(timeout=0.5)
    if not acquired:
        logger.error("Could not acquire display lock for blit - aborting")
        return None
    try:
        # Try to update the actual display with requested mode
        if _display:
            try:
                _display.display_image(img_to_send, mode=mode, prev_image_path=prev_image_path)
                logger.debug(f"Display update completed ({mode}): {file_label}")
                return None
            except Exception as e:
                logger.error(f"Display update failed ({mode}): {e}")
                # Fallback to auto mode if requested mode fails
                try:
                    _display.display_image(img_to_send, mode='auto', prev_image_path=None)
                    logger.info(f"Fallback display update completed (auto): {file_label}")
                    return None
                except Exception as e2:
                    logger.error(f"Fallback display update also failed: {e2}")
                    # In case of persistent failure, raise so higher-level logic can react
                    raise
        else:
            logger.warning("No display available - image not sent to hardware (in-memory only)")
        return None
    finally:
        _display_lock.release()


def partial_update(_rect: Tuple[int, int, int, int]):
    """Trigger partial refresh of display region."""
    global _display, _display_lock
    acquired = _display_lock.acquire(timeout=1.0)
    if not acquired:
        logger.error("Could not acquire display lock for partial_update")
        return False
    try:
        if _display:
            try:
                logger.debug(f"Partial update requested for region {_rect}")
                return True
            except Exception as e:
                logger.error(f"Partial update failed: {e}")
                return False
        return True
    finally:
        _display_lock.release()


def full_update():
    """Trigger full refresh of the display."""
    global _display, _display_lock
    acquired = _display_lock.acquire(timeout=5.0)
    if not acquired:
        logger.error("Could not acquire display lock for full_update")
        return False
    try:
        if _display:
            try:
                # Re-display current frame buffer with full update
                _display.display_image(_display.frame_buf, mode='full')
                logger.info("Full display refresh completed")
                return True
            except Exception as e:
                logger.error(f"Full update failed: {e}")
                return False
        return True
    finally:
        _display_lock.release()


def clear_display():
    """Clear the display to white."""
    global _display, _display_lock
    acquired = _display_lock.acquire(timeout=3.0)
    if not acquired:
        logger.error("Could not acquire display lock for clear_display")
        return False
    try:
        if _display:
            try:
                _display.clear()
                logger.info("Display cleared")
                return True
            except Exception as e:
                logger.error(f"Display clear failed: {e}")
                return False
        return True
    finally:
        _display_lock.release()


def close():
    """Close display connection and cleanup."""
    global _display, _display_lock
    acquired = _display_lock.acquire(timeout=5.0)
    if not acquired:
        logger.error("Could not acquire display lock for close")
        return
    try:
        if _display:
            try:
                _display.close()
                logger.info("Display connection closed")
            except Exception as e:
                logger.error(f"Display close failed: {e}")
            finally:
                _display = None
    finally:
        _display_lock.release()


def get_display_size() -> tuple | None:
    """Return (width, height) of the initialized display, or None if no display."""
    global _display
    if _display:
        try:
            w = getattr(_display, 'width', None)
            h = getattr(_display, 'height', None)
            if w and h:
                return (int(w), int(h))
        except Exception:
            pass
    return None

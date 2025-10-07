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


def init(spi_device=0, force_simulation=False, rotate: str = None):
    """Initialize display adapter.
    
    Args:
        spi_device: SPI device number (0 for CE0, 1 for CE1)
        force_simulation: Force simulation mode for testing
    
    Returns:
        True if initialization successful
    """
    global _display
    try:
        # Hardware setup: epaper display is on CE0 (SPI device 0) by default
        # The enhanced driver will use IT8951 package if available, otherwise basic SPI
        _display = create_display(
            spi_device=spi_device,
            vcom=-2.06,
            force_simulation=force_simulation,
            prefer_enhanced=True  # Try to use IT8951 package for best results
        )
        logger.info(f"Display initialized (SPI device {spi_device})")
        return True
    except Exception as e:
        logger.error(f"Display initialization failed: {e}")
        _display = None
        return False


def blit(full_bitmap: Image.Image, file_label: str = "frame", rotate: str = None, mode: str = 'auto') -> Path:
    """Write a full-screen bitmap to the real display if available; otherwise save to /tmp.

    Hardware setup: epaper display is on CE0. Uses standalone e-paper driver for 
    optimal performance and reliability.
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

    # Always save a copy for debugging
    tmp = OUT_DIR / f"{file_label}.png"
    img_to_send.save(tmp)
    
    # Try to update the actual display with requested mode
    if _display:
        try:
            _display.display_image(img_to_send, mode=mode)
            logger.debug(f"Display update completed ({mode}): {file_label}")
        except Exception as e:
            logger.error(f"Display update failed ({mode}): {e}")
            # Fallback to auto mode if requested mode fails
            try:
                _display.display_image(img_to_send, mode='auto')
                logger.info(f"Fallback display update completed (auto): {file_label}")
            except Exception as e2:
                logger.error(f"Fallback display update also failed: {e2}")
    else:
        logger.warning("No display available - saved to file only")
    
    return tmp


def partial_update(_rect: Tuple[int, int, int, int]):
    """Trigger partial refresh of display region."""
    global _display
    if _display:
        try:
            # For standalone driver, partial updates are handled automatically
            # when display_image detects changes
            logger.debug(f"Partial update requested for region {_rect}")
            return True
        except Exception as e:
            logger.error(f"Partial update failed: {e}")
            return False
    return True


def full_update():
    """Trigger full refresh of the display."""
    global _display
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


def clear_display():
    """Clear the display to white."""
    global _display
    if _display:
        try:
            _display.clear()
            logger.info("Display cleared")
            return True
        except Exception as e:
            logger.error(f"Display clear failed: {e}")
            return False
    return True


def close():
    """Close display connection and cleanup."""
    global _display
    if _display:
        try:
            _display.close()
            logger.info("Display connection closed")
        except Exception as e:
            logger.error(f"Display close failed: {e}")
        finally:
            _display = None


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

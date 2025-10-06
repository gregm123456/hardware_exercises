"""Standalone display adapter for picker application.

This module provides a self-contained e-paper display interface without external dependencies.
Uses the standalone epaper driver for IT8951-based displays.
"""
from pathlib import Path
from typing import Tuple
import logging

from PIL import Image
from .epaper_standalone import create_display

logger = logging.getLogger(__name__)

OUT_DIR = Path("/tmp/picker_display")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Global display instance
_display = None


def init(spi_device=0, force_simulation=False):
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
        _display = create_display(
            spi_device=spi_device, 
            vcom=-2.06, 
            force_simulation=force_simulation
        )
        logger.info(f"Display initialized (SPI device {spi_device})")
        return True
    except Exception as e:
        logger.error(f"Display initialization failed: {e}")
        _display = None
        return False


def blit(full_bitmap: Image.Image, file_label: str = "frame") -> Path:
    """Write a full-screen bitmap to the real display if available; otherwise save to /tmp.

    Hardware setup: epaper display is on CE0. Uses standalone e-paper driver for 
    optimal performance and reliability.
    """
    global _display
    
    # Always save a copy for debugging
    tmp = OUT_DIR / f"{file_label}.png"
    full_bitmap.save(tmp)
    
    # Try to update the actual display
    if _display:
        try:
            # Use 'auto' mode for best quality (GC16 + DU two-pass)
            _display.display_image(full_bitmap, mode='auto')
            logger.info(f"Display updated successfully with {file_label}")
        except Exception as e:
            logger.error(f"Display update failed: {e}")
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

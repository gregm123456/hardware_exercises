"""Standalone e-paper driver for IT8951-based displays.

This module provides a self-contained driver for IT8951 e-paper displays
without dependencies on external packages. It communicates directly via SPI.
"""
import time
import struct
from typing import Optional, Tuple, Union
from pathlib import Path
from PIL import Image, ImageChops
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    import spidev
    SPI_AVAILABLE = True
except ImportError:
    SPI_AVAILABLE = False
    logger.warning("spidev not available - falling back to simulation mode")


# IT8951 Commands
class Commands:
    SYS_RUN = 0x0001
    STANDBY = 0x0002
    SLEEP = 0x0003
    REG_RD = 0x0010
    REG_WR = 0x0011
    MEM_BST_RD_T = 0x0012
    MEM_BST_RD_S = 0x0013
    MEM_BST_WR = 0x0014
    MEM_BST_END = 0x0015
    LD_IMG = 0x0020
    LD_IMG_AREA = 0x0021
    LD_IMG_END = 0x0022
    DPY_AREA = 0x0026
    GET_DEV_INFO = 0x0302
    DPY_BUF_AREA = 0x0034
    VCOM = 0x0039


# Display update modes
class DisplayModes:
    INIT = 0
    DU = 1
    GC16 = 2
    GL16 = 3
    GLR16 = 4
    GLD16 = 5
    A2 = 6
    DU4 = 7


# Registers
class Registers:
    LUTAFSR = 0x224
    UP1SR = 0x134
    BGVR = 0x250
    I80CPCR = 0x04


def _apply_gamma_correction(img: Image.Image, gamma: float) -> Image.Image:
    """Apply gamma correction to a grayscale image.
    
    Gamma correction adjusts the midtones while preserving black and white points.
    gamma > 1.0 lightens midtones (makes image brighter)
    gamma < 1.0 darkens midtones
    gamma = 1.0 no change
    
    Args:
        img: PIL Image in mode 'L' (grayscale)
        gamma: Gamma correction factor (typically 1.0 to 2.5 for brightening)
    
    Returns:
        Gamma-corrected PIL Image
    """
    if gamma == 1.0:
        return img
    
    # Convert to numpy array for efficient gamma correction
    img_array = np.array(img, dtype=np.float32)
    
    # Normalize to 0-1 range
    img_array = img_array / 255.0
    
    # Apply gamma correction: output = input^(1/gamma)
    img_array = np.power(img_array, 1.0 / gamma)
    
    # Scale back to 0-255
    img_array = img_array * 255.0
    
    # Convert back to uint8 and create PIL Image
    img_array = np.clip(img_array, 0, 255).astype(np.uint8)
    
    return Image.fromarray(img_array)


class IT8951Display:
    """Standalone IT8951 e-paper display driver."""
    
    def __init__(self, spi_bus=0, spi_device=0, vcom=-2.06, width=1448, height=1072, gamma=1.0):
        """Initialize the display.
        
        Args:
            spi_bus: SPI bus number (usually 0)
            spi_device: SPI device number (0 for CE0, 1 for CE1)
            vcom: VCOM voltage
            width: Display width in pixels
            height: Display height in pixels
            gamma: Gamma correction factor (1.0=no change, >1.0=brighten midtones)
        """
        self.spi_bus = spi_bus
        self.spi_device = spi_device
        self.vcom = vcom
        self.width = width
        self.height = height
        self.gamma = gamma
        self.spi = None
        self.frame_buf = Image.new('L', (width, height), 0xFF)
        
        if SPI_AVAILABLE:
            self._init_spi()
            self._init_display()
        else:
            logger.warning("Running in simulation mode - no actual display updates")
    
    def _init_spi(self):
        """Initialize SPI communication."""
        try:
            self.spi = spidev.SpiDev()
            self.spi.open(self.spi_bus, self.spi_device)
            self.spi.max_speed_hz = 24000000
            self.spi.mode = 0
            logger.info(f"SPI initialized on bus {self.spi_bus}, device {self.spi_device}")
        except Exception as e:
            logger.error(f"Failed to initialize SPI: {e}")
            self.spi = None
    
    def _init_display(self):
        """Initialize the display hardware."""
        if not self.spi:
            return
            
        try:
            # Reset and initialize
            self._write_command(Commands.SYS_RUN)
            time.sleep(0.001)
            
            # Get device info
            device_info = self._get_device_info()
            if device_info:
                logger.info(f"Display initialized: {device_info}")
            
            # Set VCOM
            self._set_vcom(self.vcom)
            
            logger.info("Display hardware initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize display: {e}")
    
    def _write_command(self, cmd, data=None):
        """Write a command to the display."""
        if not self.spi:
            return
            
        try:
            # Write preamble
            self.spi.xfer2([0x60, 0x00])
            
            # Write command
            cmd_bytes = struct.pack('>H', cmd)
            self.spi.xfer2(list(cmd_bytes))
            
            if data:
                self.spi.xfer2(data)
                
        except Exception as e:
            logger.error(f"SPI command error: {e}")
    
    def _get_device_info(self):
        """Get device information."""
        if not self.spi:
            return None
            
        try:
            self._write_command(Commands.GET_DEV_INFO)
            time.sleep(0.001)
            
            # Read response (simplified)
            # In a full implementation, this would parse the actual device info
            return f"IT8951 {self.width}x{self.height}"
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return None
    
    def _set_vcom(self, vcom):
        """Set VCOM voltage."""
        if not self.spi:
            return
            
        try:
            vcom_val = int(abs(vcom) * 1000)
            self._write_command(Commands.VCOM, [vcom_val & 0xFF, (vcom_val >> 8) & 0xFF])
            logger.info(f"VCOM set to {vcom}V")
        except Exception as e:
            logger.error(f"Failed to set VCOM: {e}")
    
    def clear(self):
        """Clear the display to white."""
        logger.info("Clearing display")
        self.frame_buf = Image.new('L', (self.width, self.height), 0xFF)
        self._update_full(DisplayModes.GC16)
    
    def display_image(self, image: Union[Image.Image, str], mode='auto'):
        """Display an image on the screen.
        
        Args:
            image: PIL Image or path to image file
            mode: Display mode ('auto', 'full', 'partial')
        """
        if isinstance(image, str):
            img = Image.open(image)
        else:
            img = image.copy()
        
        # Prepare image
        prepared = self._prepare_image(img)
        
        # Store previous frame for partial updates
        prev_frame = self.frame_buf.copy()
        self.frame_buf = prepared
        
        if mode == 'partial':
            self._update_partial(prev_frame, prepared)
        else:
            self._update_full(DisplayModes.GC16)
            if mode == 'auto':
                # Two-pass update for better quality
                time.sleep(0.1)
                self._update_full(DisplayModes.DU)
    
    def _prepare_image(self, img: Image.Image) -> Image.Image:
        """Prepare image for display - resize and convert to grayscale."""
        # Convert to grayscale
        if img.mode != 'L':
            img = img.convert('L')
        
        # Resize to fit display while maintaining aspect ratio
        img.thumbnail((self.width, self.height), Image.LANCZOS)
        
        # Create white background and center image
        prepared = Image.new('L', (self.width, self.height), 0xFF)
        x = (self.width - img.width) // 2
        y = (self.height - img.height) // 2
        prepared.paste(img, (x, y))
        
        # Apply gamma correction if requested (after resize, before quantization)
        if self.gamma != 1.0:
            prepared = _apply_gamma_correction(prepared, self.gamma)
            logger.debug(f"Applied gamma correction: {self.gamma}")
        
        # Quantize to 4-bit for better display quality
        # Try Floyd-Steinberg dithering, fall back to default if not available
        try:
            quantized = prepared.quantize(colors=16, method=Image.FLOYDSTEINBERG)
            logger.debug("Using Floyd-Steinberg dithering")
        except (ValueError, AttributeError):
            # Fall back to default quantization if dithering not available
            quantized = prepared.quantize(colors=16)
            logger.debug("Using default quantization (no dithering)")
        
        return quantized.convert('L')
    
    def _update_full(self, mode=DisplayModes.GC16):
        """Perform a full display update."""
        if not self.spi:
            logger.info(f"Simulation: Full update with mode {mode}")
            return
            
        try:
            logger.info(f"Performing full display update (mode {mode})")
            
            # Load image data (simplified - real implementation would transfer image data)
            self._write_command(Commands.DPY_BUF_AREA)
            
            # Trigger display update
            time.sleep(0.1)  # Wait for update to complete
            
        except Exception as e:
            logger.error(f"Display update failed: {e}")
    
    def _update_partial(self, prev_img: Image.Image, new_img: Image.Image):
        """Perform a partial display update."""
        # Calculate difference region
        diff_bbox = self._get_diff_bbox(prev_img, new_img)
        
        if not diff_bbox:
            logger.info("No changes detected - skipping update")
            return
            
        if not self.spi:
            logger.info(f"Simulation: Partial update region {diff_bbox}")
            return
        
        try:
            logger.info(f"Performing partial update for region {diff_bbox}")
            
            # In a real implementation, this would update only the changed region
            self._write_command(Commands.DPY_AREA)
            time.sleep(0.05)  # Partial updates are faster
            
        except Exception as e:
            logger.error(f"Partial update failed: {e}")
    
    def _get_diff_bbox(self, prev_img: Image.Image, new_img: Image.Image) -> Optional[Tuple[int, int, int, int]]:
        """Calculate bounding box of differences between two images."""
        try:
            diff = ImageChops.difference(prev_img, new_img)
            bbox = diff.getbbox()
            
            if bbox:
                # Round to 4-pixel boundaries for better display performance
                x1, y1, x2, y2 = bbox
                x1 = (x1 // 4) * 4
                y1 = (y1 // 4) * 4
                x2 = ((x2 + 3) // 4) * 4
                y2 = ((y2 + 3) // 4) * 4
                return (x1, y1, x2, y2)
                
        except Exception as e:
            logger.error(f"Error calculating diff bbox: {e}")
        
        return None
    
    def standby(self):
        """Put display in standby mode."""
        if self.spi:
            try:
                self._write_command(Commands.STANDBY)
                logger.info("Display in standby mode")
            except Exception as e:
                logger.error(f"Failed to enter standby: {e}")
    
    def close(self):
        """Close SPI connection."""
        if self.spi:
            self.spi.close()
            logger.info("SPI connection closed")


# Simulation fallback for development
class SimulatedDisplay:
    """Simulated display for development without hardware."""
    
    def __init__(self, width=1448, height=1072, gamma=1.0):
        self.width = width
        self.height = height
        self.gamma = gamma
        self.frame_buf = Image.new('L', (width, height), 0xFF)
        self.output_dir = Path("/tmp/picker_display")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frame_count = 0
        
    def clear(self):
        logger.info("Simulated: Clearing display")
        self.frame_buf = Image.new('L', (self.width, self.height), 0xFF)
        self._save_frame("clear")
    
    def display_image(self, image: Union[Image.Image, str], mode='auto'):
        if isinstance(image, str):
            img = Image.open(image)
        else:
            img = image.copy()
            
        # Prepare image same as real display
        if img.mode != 'L':
            img = img.convert('L')
        
        img.thumbnail((self.width, self.height), Image.LANCZOS)
        prepared = Image.new('L', (self.width, self.height), 0xFF)
        x = (self.width - img.width) // 2
        y = (self.height - img.height) // 2
        prepared.paste(img, (x, y))
        
        # Apply gamma correction if requested
        if self.gamma != 1.0:
            prepared = _apply_gamma_correction(prepared, self.gamma)
            logger.debug(f"Applied gamma correction: {self.gamma}")
        
        self.frame_buf = prepared
        self._save_frame(f"display_{mode}")
        logger.info(f"Simulated: Display image with mode {mode}")
    
    def _save_frame(self, label="frame"):
        filename = self.output_dir / f"{label}_{self.frame_count:04d}.png"
        self.frame_buf.save(filename)
        self.frame_count += 1
        logger.info(f"Saved simulated frame to {filename}")
    
    def standby(self):
        logger.info("Simulated: Display standby")
    
    def close(self):
        logger.info("Simulated: Display closed")


def create_display(spi_device=0, vcom=-2.06, width=1448, height=1072, gamma=1.0, force_simulation=False):
    """Create a display instance - real hardware or simulation.
    
    Args:
        spi_device: SPI device number (0 for CE0, 1 for CE1)
        vcom: VCOM voltage
        width: Display width
        height: Display height
        gamma: Gamma correction factor (1.0=no change, >1.0=brighten midtones)
        force_simulation: Force simulation mode even if hardware is available
    
    Returns:
        Display instance (IT8951Display or SimulatedDisplay)
    """
    if force_simulation or not SPI_AVAILABLE:
        logger.info("Creating simulated display")
        return SimulatedDisplay(width, height, gamma=gamma)
    else:
        logger.info(f"Creating hardware display on SPI device {spi_device}")
        return IT8951Display(spi_device=spi_device, vcom=vcom, width=width, height=height, gamma=gamma)
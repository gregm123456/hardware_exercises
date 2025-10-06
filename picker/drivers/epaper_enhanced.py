"""Enhanced standalone e-paper driver that can optionally use IT8951 package.

This provides a self-contained fallback while allowing use of the IT8951 package
when available for better hardware support.
"""
import logging
from typing import Union, Optional
from PIL import Image
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import display drivers in order of preference
DISPLAY_MODE = "none"
update_waveshare_available = False
IT8951_AVAILABLE = False

# First try update_waveshare (most likely to work)
try:
    import sys
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent
    
    # Add project root to path so we can import update_waveshare
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    from update_waveshare.core import display_image, blank_screen
    from update_waveshare._device import create_device as create_waveshare_device
    update_waveshare_available = True
    DISPLAY_MODE = "update_waveshare"
    print("DEBUG: update_waveshare available - using existing drivers")
    logger.info("update_waveshare available - using existing drivers")
except ImportError as e:
    print(f"DEBUG: update_waveshare not available: {e}")

# Fallback to IT8951 if update_waveshare fails
if not update_waveshare_available:
    try:
        # Try direct IT8951 import
        it8951_src = project_root / 'IT8951' / 'src'
        if it8951_src.exists():
            sys.path.insert(0, str(it8951_src))
        
        from IT8951.display import AutoEPDDisplay, VirtualEPDDisplay
        from IT8951.constants import DisplayModes
        IT8951_AVAILABLE = True
        DISPLAY_MODE = "IT8951"
        print("DEBUG: IT8951 import successful!")
        logger.info("IT8951 package available - using enhanced driver")
    except ImportError as e:
        print(f"DEBUG: IT8951 import failed: {e}")
        logger.info(f"IT8951 package not available: {e} - using basic SPI driver")

# Fallback to our basic SPI implementation
try:
    import spidev
    SPI_AVAILABLE = True
except ImportError:
    SPI_AVAILABLE = False


class WaveshareDisplay:
    """Display using existing update_waveshare drivers."""
    
    def __init__(self, spi_device=0, vcom=-2.06, width=1448, height=1072, virtual=False):
        self.width = width
        self.height = height
        self.virtual = virtual
        
        if update_waveshare_available:
            try:
                self.device = create_waveshare_device(vcom=vcom, virtual=virtual)
                self.width = getattr(self.device, 'width', width)
                self.height = getattr(self.device, 'height', height)
                logger.info(f"Waveshare display initialized: {self.width}x{self.height}")
            except Exception as e:
                logger.error(f"Failed to create waveshare device: {e}")
                raise
        else:
            raise RuntimeError("update_waveshare not available")
    
    def clear(self):
        """Clear the display."""
        logger.info("Clearing display (waveshare)")
        if update_waveshare_available:
            try:
                blank_screen(device=self.device, virtual=self.virtual)
            except Exception as e:
                logger.error(f"Clear failed: {e}")
    
    def display_image(self, image: Union[Image.Image, str], mode='auto'):
        """Display an image."""
        if isinstance(image, str):
            img_path = image
        else:
            # Save PIL image to temporary file
            temp_path = "/tmp/picker_temp_display.png"
            image.save(temp_path)
            img_path = temp_path
        
        try:
            logger.info(f"Displaying image with waveshare (mode: {mode})")
            regions = display_image(
                img_path, 
                device=self.device, 
                virtual=self.virtual, 
                mode=mode,
                vcom=-2.06  # Use consistent VCOM
            )
            logger.info(f"Display update completed, regions: {regions}")
        except Exception as e:
            logger.error(f"Display update failed: {e}")
            raise
    
    def close(self):
        """Close display connection."""
        if hasattr(self.device, 'epd') and hasattr(self.device.epd, 'standby'):
            try:
                self.device.epd.standby()
            except:
                pass
        logger.info("Waveshare display closed")


class EnhancedIT8951Display:
    """Enhanced display using IT8951 package when available."""
    
    def __init__(self, spi_device=0, vcom=-2.06, width=1448, height=1072, virtual=False):
        self.width = width
        self.height = height
        self.virtual = virtual
        
        if IT8951_AVAILABLE:
            if virtual:
                self.display = VirtualEPDDisplay(dims=(width, height))
            else:
                self.display = AutoEPDDisplay(vcom=vcom)
                self.width = self.display.width
                self.height = self.display.height
            logger.info(f"Enhanced display initialized: {self.width}x{self.height}")
        else:
            raise RuntimeError("IT8951 package not available for enhanced driver")
    
    def clear(self):
        """Clear the display."""
        logger.info("Clearing display")
        if hasattr(self.display, 'clear'):
            self.display.clear()
        else:
            # Fallback: fill with white and update
            self.display.frame_buf = Image.new('L', (self.width, self.height), 0xFF)
            if IT8951_AVAILABLE:
                self.display.draw_full(DisplayModes.GC16)
    
    def display_image(self, image: Union[Image.Image, str], mode='auto'):
        """Display an image."""
        if isinstance(image, str):
            img = Image.open(image)
        else:
            img = image.copy()
        
        # Prepare image
        prepared = self._prepare_image(img)
        
        # Update display
        self.display.frame_buf.paste(prepared)
        
        if mode == 'auto' or mode == 'full':
            if IT8951_AVAILABLE:
                self.display.draw_full(DisplayModes.GC16)
                if mode == 'auto':
                    # Two-pass for better quality
                    self.display.draw_full(DisplayModes.DU)
        elif mode == 'partial':
            if IT8951_AVAILABLE:
                self.display.draw_partial(DisplayModes.DU)
        
        logger.info(f"Display updated with mode {mode}")
    
    def _prepare_image(self, img: Image.Image) -> Image.Image:
        """Prepare image for display."""
        if img.mode != 'L':
            img = img.convert('L')
        
        img.thumbnail((self.width, self.height), Image.LANCZOS)
        
        prepared = Image.new('L', (self.width, self.height), 0xFF)
        x = (self.width - img.width) // 2
        y = (self.height - img.height) // 2
        prepared.paste(img, (x, y))
        
        return prepared
    
    def close(self):
        """Close display connection."""
        if hasattr(self.display, 'epd') and hasattr(self.display.epd, 'standby'):
            try:
                self.display.epd.standby()
            except:
                pass
        logger.info("Display closed")


class BasicSPIDisplay:
    """Basic SPI display implementation."""
    
    def __init__(self, spi_device=0, vcom=-2.06, width=1448, height=1072):
        self.width = width
        self.height = height
        self.frame_buf = Image.new('L', (width, height), 0xFF)
        
        if SPI_AVAILABLE:
            self.spi = spidev.SpiDev()
            self.spi.open(0, spi_device)
            self.spi.max_speed_hz = 24000000
            self.spi.mode = 0
            logger.info(f"Basic SPI display initialized on CE{spi_device}")
        else:
            self.spi = None
            logger.warning("SPI not available - display will not update")
    
    def clear(self):
        """Clear display to white."""
        logger.info("Clearing display (basic SPI)")
        self.frame_buf = Image.new('L', (self.width, self.height), 0xFF)
        # Basic clear - just log for now since IT8951 protocol is complex
        logger.info("Display cleared (basic mode)")
    
    def display_image(self, image: Union[Image.Image, str], mode='auto'):
        """Display an image."""
        if isinstance(image, str):
            img = Image.open(image)
        else:
            img = image.copy()
        
        prepared = self._prepare_image(img)
        self.frame_buf = prepared
        
        logger.info(f"Image prepared for display (basic SPI mode: {mode})")
        # In basic mode, we can't actually update the display without
        # implementing the full IT8951 protocol
    
    def _prepare_image(self, img: Image.Image) -> Image.Image:
        """Prepare image for display."""
        if img.mode != 'L':
            img = img.convert('L')
        
        img.thumbnail((self.width, self.height), Image.LANCZOS)
        
        prepared = Image.new('L', (self.width, self.height), 0xFF)
        x = (self.width - img.width) // 2
        y = (self.height - img.height) // 2
        prepared.paste(img, (x, y))
        
        return prepared
    
    def close(self):
        """Close SPI connection."""
        if self.spi:
            self.spi.close()
        logger.info("Basic SPI display closed")


class SimulatedDisplay:
    """Simulated display for development."""
    
    def __init__(self, width=1448, height=1072):
        self.width = width
        self.height = height
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
            
        if img.mode != 'L':
            img = img.convert('L')
        
        img.thumbnail((self.width, self.height), Image.LANCZOS)
        prepared = Image.new('L', (self.width, self.height), 0xFF)
        x = (self.width - img.width) // 2
        y = (self.height - img.height) // 2
        prepared.paste(img, (x, y))
        
        self.frame_buf = prepared
        self._save_frame(f"display_{mode}")
        logger.info(f"Simulated: Display image with mode {mode}")
    
    def _save_frame(self, label="frame"):
        filename = self.output_dir / f"{label}_{self.frame_count:04d}.png"
        self.frame_buf.save(filename)
        self.frame_count += 1
        logger.info(f"Saved simulated frame to {filename}")
    
    def close(self):
        logger.info("Simulated: Display closed")


def create_display(spi_device=0, vcom=-2.06, width=1448, height=1072, force_simulation=False, prefer_enhanced=True):
    """Create the best available display instance.
    
    Args:
        spi_device: SPI device number (0 for CE0, 1 for CE1)
        vcom: VCOM voltage
        width: Display width
        height: Display height
        force_simulation: Force simulation mode
        prefer_enhanced: Prefer advanced drivers if available
    
    Returns:
        Display instance
    """
    if force_simulation:
        logger.info("Creating simulated display")
        return SimulatedDisplay(width, height)
    
    # Try update_waveshare first (most likely to work)
    if prefer_enhanced and update_waveshare_available:
        try:
            logger.info(f"Creating Waveshare display on SPI device {spi_device}")
            return WaveshareDisplay(spi_device=spi_device, vcom=vcom, width=width, height=height)
        except Exception as e:
            logger.warning(f"Waveshare display failed: {e} - trying next option")
    
    # Try IT8951 as fallback
    if prefer_enhanced and IT8951_AVAILABLE:
        try:
            logger.info(f"Creating enhanced IT8951 display on SPI device {spi_device}")
            return EnhancedIT8951Display(spi_device=spi_device, vcom=vcom, width=width, height=height)
        except Exception as e:
            logger.warning(f"Enhanced display failed: {e} - falling back to basic SPI")
    
    # Basic SPI as last resort
    if SPI_AVAILABLE:
        logger.info(f"Creating basic SPI display on device {spi_device}")
        return BasicSPIDisplay(spi_device=spi_device, vcom=vcom, width=width, height=height)
    else:
        logger.info("No SPI available - creating simulated display")
        return SimulatedDisplay(width, height)
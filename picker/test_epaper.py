#!/usr/bin/env python3
"""Test script for the standalone e-paper display driver.

Run this on the Pi to test if the display hardware is working properly.
"""
import sys
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Add parent directory to path to import picker modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from picker.drivers.epaper_standalone import create_display

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_test_image(width=1448, height=1072, text="E-PAPER TEST"):
    """Create a simple test image with text and shapes."""
    img = Image.new('L', (width, height), 255)  # White background
    draw = ImageDraw.Draw(img)
    
    # Draw border
    draw.rectangle([10, 10, width-10, height-10], outline=0, width=5)
    
    # Draw test text
    try:
        # Try to use a larger font if available
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        # Fall back to default font
        font = ImageFont.load_default()
    
    # Center the text
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    draw.text((x, y), text, fill=0, font=font)
    
    # Draw some shapes for visual reference
    draw.circle([width//4, height//4], 50, outline=0, width=3)
    draw.rectangle([3*width//4-50, height//4-50, 3*width//4+50, height//4+50], outline=0, width=3)
    draw.line([width//4, 3*height//4, 3*width//4, 3*height//4], fill=0, width=5)
    
    return img


def test_display_modes():
    """Test different display modes and operations."""
    logger.info("=== E-Paper Display Test ===")
    
    # Test 1: Force simulation mode to verify code path
    logger.info("Test 1: Creating simulated display")
    sim_display = create_display(force_simulation=True)
    test_img = create_test_image(text="SIMULATION TEST")
    sim_display.display_image(test_img, mode='auto')
    sim_display.close()
    logger.info("Simulation test completed")
    
    # Test 2: Try hardware display on CE0 (default for e-paper)
    logger.info("Test 2: Creating hardware display on CE0")
    hw_display = create_display(spi_device=0, force_simulation=False)
    
    # Test clear
    logger.info("Clearing display...")
    hw_display.clear()
    
    # Test display with different modes
    test_img = create_test_image(text="HARDWARE TEST")
    
    logger.info("Testing 'full' mode...")
    hw_display.display_image(test_img, mode='full')
    
    input("Press Enter to test 'auto' mode...")
    logger.info("Testing 'auto' mode...")
    test_img2 = create_test_image(text="AUTO MODE TEST")
    hw_display.display_image(test_img2, mode='auto')
    
    input("Press Enter to test partial update...")
    logger.info("Testing partial update...")
    # Make a small change for partial update
    test_img3 = test_img2.copy()
    draw = ImageDraw.Draw(test_img3)
    draw.rectangle([50, 50, 200, 150], fill=128)  # Gray rectangle
    hw_display.display_image(test_img3, mode='partial')
    
    input("Press Enter to clear and finish...")
    hw_display.clear()
    hw_display.close()
    
    logger.info("=== Display test completed ===")


def test_spi_devices():
    """Test both SPI devices to see which one responds."""
    logger.info("=== Testing SPI Devices ===")
    
    for device in [0, 1]:
        logger.info(f"Testing SPI device CE{device}")
        try:
            display = create_display(spi_device=device, force_simulation=False)
            test_img = create_test_image(text=f"SPI CE{device} TEST")
            display.display_image(test_img, mode='full')
            display.close()
            logger.info(f"CE{device} test completed")
        except Exception as e:
            logger.error(f"CE{device} test failed: {e}")
    
    logger.info("=== SPI device tests completed ===")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test e-paper display")
    parser.add_argument("--test-spi", action="store_true", help="Test both SPI devices")
    parser.add_argument("--quick", action="store_true", help="Quick test without user prompts")
    args = parser.parse_args()
    
    if args.test_spi:
        test_spi_devices()
    elif args.quick:
        logger.info("Quick display test")
        display = create_display(spi_device=0)
        test_img = create_test_image(text="QUICK TEST")
        display.display_image(test_img, mode='auto')
        display.close()
    else:
        test_display_modes()
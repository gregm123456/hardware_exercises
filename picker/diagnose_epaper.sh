#!/bin/bash
# E-paper Display Diagnostic Script for Raspberry Pi
# Run this on your Pi to diagnose display connectivity issues

echo "=== E-Paper Display Diagnostics ==="
echo

# Check SPI is enabled
echo "1. Checking SPI status:"
if lsmod | grep -q spi_bcm2835; then
    echo "   ✓ SPI kernel module loaded"
else
    echo "   ✗ SPI kernel module NOT loaded"
    echo "   → Run 'sudo raspi-config' and enable SPI under Interface Options"
fi

# Check SPI devices
echo "2. Checking SPI devices:"
if [ -c /dev/spidev0.0 ]; then
    echo "   ✓ /dev/spidev0.0 (CE0) exists"
else
    echo "   ✗ /dev/spidev0.0 (CE0) missing"
fi

if [ -c /dev/spidev0.1 ]; then
    echo "   ✓ /dev/spidev0.1 (CE1) exists"
else
    echo "   ✗ /dev/spidev0.1 (CE1) missing"
fi

# Check SPI configuration
echo "3. SPI configuration in /boot/config.txt:"
if grep -q "^dtparam=spi=on" /boot/config.txt; then
    echo "   ✓ SPI enabled in config.txt"
else
    echo "   ✗ SPI not enabled in config.txt"
    echo "   → Add 'dtparam=spi=on' to /boot/config.txt"
fi

# Check GPIO permissions
echo "4. Checking user permissions:"
if groups | grep -q gpio; then
    echo "   ✓ User is in gpio group"
else
    echo "   ✗ User not in gpio group"
    echo "   → Run 'sudo usermod -a -G gpio $USER' and log out/in"
fi

if groups | grep -q spi; then
    echo "   ✓ User is in spi group"
else
    echo "   ✗ User not in spi group"
    echo "   → Run 'sudo usermod -a -G spi $USER' and log out/in"
fi

# Check Python packages
echo "5. Checking Python packages:"
if [ -f "../.venv/bin/activate" ]; then
    source ../.venv/bin/activate 2>/dev/null
    echo "   ✓ Found .venv in parent directory"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate 2>/dev/null
    echo "   ✓ Found .venv in current directory"
else
    echo "   Warning: No .venv found"
fi

if python -c "import spidev" 2>/dev/null; then
    echo "   ✓ spidev package available"
else
    echo "   ✗ spidev package missing"
    echo "   → Run 'pip install spidev'"
fi

if python -c "from PIL import Image" 2>/dev/null; then
    echo "   ✓ Pillow package available"
else
    echo "   ✗ Pillow package missing"
    echo "   → Run 'pip install Pillow'"
fi

# Test SPI communication
echo "6. Testing SPI communication:"
if [ -c /dev/spidev0.0 ]; then
    # Simple SPI test - try to open and close the device
    python3 -c "
import spidev
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)  # CE0
    spi.close()
    print('   ✓ SPI CE0 communication test passed')
except Exception as e:
    print(f'   ✗ SPI CE0 test failed: {e}')
" 2>/dev/null || echo "   ✗ SPI CE0 test failed - Python/spidev issue"
fi

if [ -c /dev/spidev0.1 ]; then
    python3 -c "
import spidev
try:
    spi = spidev.SpiDev()
    spi.open(0, 1)  # CE1
    spi.close()
    print('   ✓ SPI CE1 communication test passed')
except Exception as e:
    print(f'   ✗ SPI CE1 test failed: {e}')
" 2>/dev/null || echo "   ✗ SPI CE1 test failed - Python/spidev issue"
fi

echo
echo "=== Hardware Wiring Check ==="
echo "Verify your e-paper display connections:"
echo "  Display → Pi"
echo "  VCC     → 3.3V"
echo "  GND     → GND"
echo "  DIN     → GPIO 10 (MOSI)"
echo "  CLK     → GPIO 11 (SCLK)"
echo "  CS      → GPIO 8  (CE0) ← Should be CE0 for display"
echo "  DC      → GPIO 25"
echo "  RST     → GPIO 17"
echo "  BUSY    → GPIO 24"
echo
echo "ADC (MCP3008) should be on CE1:"
echo "  CS      → GPIO 7  (CE1) ← Should be CE1 for ADC"
echo

echo "=== Next Steps ==="
echo "1. If SPI issues found, fix them and reboot"
echo "2. Run the hardware test: 'cd picker && python test_epaper.py --test-spi'"
echo "3. Check wiring matches the pin assignments above"
echo "4. Try running picker without --force-simulation: 'cd .. && python picker/run_picker.py --simulate --verbose'"
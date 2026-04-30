#!/bin/bash
# Setup script for Picker on Raspberry Pi
# Run this to install all dependencies and set up the environment

echo "=== Setting up Picker environment on Raspberry Pi ==="

# Check if we're in a virtual environment
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "❌ No virtual environment active!"
    echo "On Raspberry Pi 5, please create one with system site packages:"
    echo "  python -m venv .venv --system-site-packages"
    echo "  source .venv/bin/activate"
    exit 1
fi

# Detect Pi 5
if grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null; then
    echo "🚀 Raspberry Pi 5 detected. Ensuring hardware compatibility..."
    # Uninstall conflicting venv packages to use system versions
    pip uninstall -y RPi.GPIO spidev 2>/dev/null
fi

echo "✓ Virtual environment: $VIRTUAL_ENV"

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install --upgrade pip
pip install -r picker/requirements.txt

# Install IT8951 package from the submodule
echo "🔧 Installing IT8951 package..."
if [ -d "IT8951" ]; then
    cd IT8951
    pip install -e .
    cd ..
    echo "✓ IT8951 installed from submodule"
else
    echo "❌ IT8951 directory not found!"
    echo "Run: git submodule update --init --recursive"
    exit 1
fi

# Test the installation
echo "🧪 Testing installation..."
python -c "
try:
    import IT8951
    print('✓ IT8951 package imported successfully')
except ImportError as e:
    print(f'❌ IT8951 import failed: {e}')

try:
    from picker.drivers.epaper_enhanced import DISPLAY_MODE
    print(f'✓ Picker display mode: {DISPLAY_MODE}')
except ImportError as e:
    print(f'❌ Picker import failed: {e}')

try:
    import spidev
    print('✓ spidev available')
except ImportError:
    print('❌ spidev not available - install with: pip install spidev')
"

echo "🎯 Testing e-paper display..."
PYTHONPATH=. python picker/test_epaper.py --quick

echo "=== Setup complete! ==="
echo "To run the picker:"
echo "  PYTHONPATH=. python picker/run_picker.py --simulate --verbose"
echo "  # Remove --simulate to use real hardware"
#!/usr/bin/env python3
"""Test different display waveform modes to isolate banding issue."""

import sys
from pathlib import Path

# Ensure we can import the packages
parent = str(Path(__file__).resolve().parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

from update_waveshare._device import create_device
from update_waveshare.core import _load_and_prepare
from IT8951.constants import DisplayModes

def test_waveform_modes():
    """Test different waveform modes directly."""
    
    print("Testing different waveform modes...")
    device = create_device()
    
    # Prepare the image
    target_size = (device.width, device.height)
    img = _load_and_prepare("gradient.png", target_size, target_bpp=4, dither=True)
    
    # Test different waveform modes
    modes_to_test = [
        ("GC16 only", DisplayModes.GC16),
        ("GL16 only", DisplayModes.GL16), 
        ("GLR16 only", DisplayModes.GLR16),
        ("GLD16 only", DisplayModes.GLD16),
    ]
    
    for desc, mode in modes_to_test:
        print(f"\n=== Testing {desc} ===")
        input("Press ENTER to start this test...")
        
        try:
            device.frame_buf.paste(img)
            device.draw_full(mode)
            print(f"Applied {desc}")
            print("How does the gradient look?")
            input("Press ENTER to continue to next test...")
            
        except Exception as e:
            print(f"Error with {desc}: {e}")
    
    print("\nTesting complete!")

if __name__ == "__main__":
    test_waveform_modes()

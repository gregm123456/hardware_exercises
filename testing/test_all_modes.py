#!/usr/bin/env python3
"""
Test each display mode individually to see if any gives HIGH quality.
"""
import time
from update_waveshare._device import create_device
from IT8951.constants import DisplayModes

# All available display modes
MODES_TO_TEST = [
    ("INIT", DisplayModes.INIT),
    ("DU", DisplayModes.DU),
    ("GC16", DisplayModes.GC16),
    ("GL16", DisplayModes.GL16),
    ("GLR16", DisplayModes.GLR16),
    ("GLD16", DisplayModes.GLD16),
    ("A2", DisplayModes.A2),
    ("DU4", DisplayModes.DU4),
]

def test_mode(mode_name, mode_value):
    """Test a single display mode"""
    print(f"Testing mode: {mode_name} (value: {mode_value})")
    
    device = create_device(vcom=-2.06)
    
    try:
        # Load the image
        from update_waveshare.core import _load_and_prepare
        target_size = (device.width, device.height)
        
        # Try both 4BPP and 8BPP preparations
        for bpp, desc in [(4, "4BPP"), (8, "8BPP")]:
            print(f"  Testing {mode_name} with {desc}...")
            
            img = _load_and_prepare("waveshare_sample.png", target_size, target_bpp=bpp, dither=True)
            device.frame_buf.paste(img)
            
            # Use the specific mode
            device.draw_full(mode_value)
            
            time.sleep(1)
            
            # Test file name
            test_file = f"test_{mode_name}_{desc.lower()}.png"
            print(f"    Result saved conceptually as: {test_file}")
            
    except Exception as e:
        print(f"  Error testing {mode_name}: {e}")
    
    finally:
        try:
            if hasattr(device, 'epd') and hasattr(device.epd, 'spi'):
                device.epd.spi.close()
        except:
            pass
        del device

def main():
    print("Testing all display modes to find HIGH quality...")
    print("After each mode, manually check the display quality!")
    print()
    
    for mode_name, mode_value in MODES_TO_TEST:
        test_mode(mode_name, mode_value)
        
        response = input(f"\nAfter {mode_name}: Is the quality HIGH? (y/n/q to quit): ").strip().lower()
        
        if response == 'y':
            print(f"SUCCESS! {mode_name} gives HIGH quality!")
            return
        elif response == 'q':
            print("Quitting test.")
            return
        
        print("Continuing to next mode...\n")
    
    print("All modes tested. None gave HIGH quality.")

if __name__ == '__main__':
    main()

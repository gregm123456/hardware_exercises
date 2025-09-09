#!/usr/bin/env python3
"""
Single sequence initialization that properly releases the device for testing.
"""
import time
from update_waveshare._device import create_device
from IT8951.constants import DisplayModes

def main():
    """
    Run one initialization sequence then exit cleanly.
    """
    print("Running advanced initialization sequence...")
    
    # Initialize the display
    device = create_device(vcom=-2.06)
    
    try:
        # Wake up the controller
        device.epd.run()
        time.sleep(0.5)
        
        # Multiple INIT cycles
        print("Running 3 INIT cycles...")
        for i in range(3):
            print(f"  INIT cycle {i+1}/3...")
            device.clear()  # Uses INIT mode
            time.sleep(0.5)
        
        # Multiple GC16 with delays
        print("Running 2 GC16 passes...")
        device.draw_full(DisplayModes.GC16)
        time.sleep(1)
        device.draw_full(DisplayModes.GC16)
        time.sleep(1)
        
        # DU pass
        print("Running DU pass...")
        device.draw_full(DisplayModes.DU)
        
        print("Advanced initialization complete.")
        
    finally:
        # Ensure device is properly released
        try:
            if hasattr(device, 'epd') and hasattr(device.epd, 'spi'):
                device.epd.spi.close()
        except:
            pass
        del device
    
    print("\nDevice released. Now test with:")
    print("python ./update_waveshare/simple_update.py waveshare_sample.png")

if __name__ == '__main__':
    main()

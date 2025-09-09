#!/usr/bin/env python3
"""
Performs a more forceful re-initialization sequence on the IT8951 display,
then immediately tests image update quality.
"""
import time
from update_waveshare.core import display_image

def main():
    """
    Main function to re-initialize the display and test quality.
    """
    print("Attempting to re-initialize display...")
    
    # Create device for reset sequence
    from update_waveshare._device import create_device
    from IT8951.constants import DisplayModes
    
    display = create_device(vcom=-2.06)

    # Wake up the controller
    display.epd.run()
    time.sleep(0.5)

    # Clear the display using INIT mode
    print("Clearing display with INIT mode...")
    display.clear()
    time.sleep(1)

    # Perform a GC16 full update to reset LUTs
    print("Performing GC16 full update...")
    display.draw_full(DisplayModes.GC16)
    time.sleep(1)

    # Perform a second GC16 full update
    print("Performing second GC16 full update...")
    display.draw_full(DisplayModes.GC16)
    time.sleep(1)

    # Finally, do a DU pass to clean up
    print("Performing DU pass...")
    display.draw_full(DisplayModes.DU)

    print("Re-initialization sequence complete.")
    print("Now testing image update quality...")
    
    # Test image update using the same device object (no GPIO conflict)
    try:
        regions = display_image('waveshare_sample.png', device=display)
        print(f"Image update complete. Updated regions: {regions}")
        print("Check display quality now!")
    except Exception as e:
        print(f"Image update failed: {e}")
    
    # Properly clean up
    try:
        if hasattr(display, 'epd'):
            display.epd.standby()
    except Exception:
        pass

if __name__ == '__main__':
    main()

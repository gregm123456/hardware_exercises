#!/usr/bin/env python3
"""Try to fully reset/reinitialize the IT8951 controller to fresh state."""

from update_waveshare._device import create_device
from IT8951.constants import DisplayModes

def main():
    print("Creating device and attempting full controller reset...")
    
    # Create device (this runs update_system_info and basic init)
    device = create_device(vcom=-2.06)
    
    print("Running INIT mode clear...")
    device.clear()  # This uses INIT mode
    
    print("Running additional GC16 initialization...")
    # Try multiple GC16 passes to establish waveform state
    device.draw_full(DisplayModes.GC16)
    device.draw_full(DisplayModes.GC16)
    
    print("Running DU pass...")
    device.draw_full(DisplayModes.DU)
    
    print("Controller reset complete.")

if __name__ == '__main__':
    main()

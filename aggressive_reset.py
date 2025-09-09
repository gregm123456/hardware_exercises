#!/usr/bin/env python3
"""
Aggressive display controller manipulation to try to restore HIGH quality state.
"""
import time
from update_waveshare._device import create_device
from IT8951.constants import DisplayModes, Registers

def try_sequence_1():
    """Try sequence 1: Multiple INIT cycles with register manipulation"""
    print("=== TRYING SEQUENCE 1: Multiple INIT cycles ===")
    device = create_device(vcom=-2.06)
    
    # Try multiple INIT cycles
    for i in range(3):
        print(f"INIT cycle {i+1}/3...")
        device.clear()  # Uses INIT mode
        time.sleep(0.5)
    
    # Try reading and resetting some registers
    try:
        print("Reading/resetting registers...")
        up0sr = device.epd.read_register(Registers.UP0SR)
        print(f"UP0SR before: {hex(up0sr)}")
        
        # Try resetting UP0SR
        device.epd.write_register(Registers.UP0SR, 0)
        time.sleep(0.1)
        
        up0sr_after = device.epd.read_register(Registers.UP0SR)
        print(f"UP0SR after: {hex(up0sr_after)}")
        
    except Exception as e:
        print(f"Register manipulation failed: {e}")
    
    # Final GC16 sequence
    print("Final GC16 sequence...")
    device.draw_full(DisplayModes.GC16)
    time.sleep(1)
    device.draw_full(DisplayModes.GC16)
    
    return device

def try_sequence_2():
    """Try sequence 2: Different VCOM and timing"""
    print("=== TRYING SEQUENCE 2: Different VCOM/timing ===")
    
    # Try slightly different VCOM
    device = create_device(vcom=-2.00)  # Slightly different from -2.06
    
    device.clear()
    time.sleep(2)  # Longer wait
    
    # Multiple GC16 with longer delays
    for i in range(2):
        print(f"GC16 pass {i+1}/2...")
        device.draw_full(DisplayModes.GC16)
        time.sleep(1)
    
    return device

def try_sequence_3():
    """Try sequence 3: Different display modes in sequence"""
    print("=== TRYING SEQUENCE 3: Different display mode sequence ===")
    device = create_device(vcom=-2.06)
    
    # Try different waveform sequence
    modes_to_try = [DisplayModes.INIT, DisplayModes.GL16, DisplayModes.GC16, DisplayModes.DU]
    
    for mode in modes_to_try:
        print(f"Trying mode: {mode}")
        device.draw_full(mode)
        time.sleep(0.5)
    
    return device

def main():
    """Try different sequences and test each one"""
    sequences = [try_sequence_1, try_sequence_2, try_sequence_3]
    
    for i, seq_func in enumerate(sequences, 1):
        print(f"\n{'='*50}")
        print(f"SEQUENCE {i}")
        print(f"{'='*50}")
        
        try:
            device = seq_func()
            print(f"\nSequence {i} complete. Now test with:")
            print("python ./update_waveshare/simple_update.py waveshare_sample.png")
            
            input(f"\nPress Enter after testing sequence {i} to continue to next sequence...")
            
        except Exception as e:
            print(f"Sequence {i} failed: {e}")
            continue

if __name__ == '__main__':
    main()

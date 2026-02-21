#!/usr/bin/env python3
"""
GPIO pin state diagnostic for rotary encoder.
Reads raw GPIO pin states and checks for noise/floating.
"""
import sys
import time

# Try to import RPi.GPIO; fall back gracefully
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    print("RPi.GPIO not available (expected on non-Pi systems)")
    sys.exit(1)

# Configured pins (hardware setup)
CLK_PIN = 22
DT_PIN = 23
SW_PIN = 27

def diagnose():
    print("=" * 60)
    print("GPIO PIN STATE DIAGNOSTIC")
    print("=" * 60)
    print(f"\nTesting pins: CLK={CLK_PIN}, DT={DT_PIN}, SW={SW_PIN}")
    print("Sampling raw GPIO state for 5 seconds...\n")
    
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(CLK_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(DT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(SW_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        print("Time\t\tCLK(22)\tDT(23)\tSW(27)\tAB-State")
        print("-" * 50)
        
        last_state = None
        change_count = 0
        t_start = time.time()
        
        while time.time() - t_start < 5.0:
            clk = GPIO.input(CLK_PIN)
            dt = GPIO.input(DT_PIN)
            sw = GPIO.input(SW_PIN)
            state = (clk << 1) | dt
            
            if state != last_state:
                change_count += 1
                elapsed = time.time() - t_start
                print(f"{elapsed:6.2f}s\t{clk}\t{dt}\t{sw}\t{state:02b} [changed]")
                last_state = state
            
            time.sleep(0.05)
        
        print("-" * 50)
        print(f"\nTotal state changes in 5s: {change_count}")
        
        if change_count == 0:
            print("✓ GPIO pins are stable (no noise detected)")
        elif change_count < 3:
            print("✓ GPIO pins are mostly stable (minor noise OK)")
        else:
            print(f"✗ WARNING: {change_count} state changes detected!")
            print("  This suggests floating pins or encoder hardware issues")
            print("  CHECK: Encoder is properly connected")
            print("  CHECK: Pull-up resistors are functioning")
            print("  CHECK: No loose wiring causing intermittent contact")
        
        # Test button with longer stable hold
        print("\nTesting button debounce (waiting for 2-second stable reading)...")
        sw_start = GPIO.input(SW_PIN)
        stable_time = 0.0
        t_start = time.time()
        while stable_time < 2.0:
            sw = GPIO.input(SW_PIN)
            if sw == sw_start:
                stable_time += 0.05
            else:
                stable_time = 0.0
                sw_start = sw
            time.sleep(0.05)
            if time.time() - t_start > 10.0:
                print("✗ Button pin is unstable (bouncing excessively)")
                break
        else:
            print(f"✓ Button pin stable at {sw_start} (not pressed={sw_start})")
        
    except Exception as e:
        print(f"✗ GPIO diagnostic failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            GPIO.cleanup([CLK_PIN, DT_PIN, SW_PIN])
        except Exception:
            pass

if __name__ == "__main__":
    diagnose()

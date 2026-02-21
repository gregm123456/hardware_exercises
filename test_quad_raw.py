#!/usr/bin/env python3
"""Raw quadrature encoder test - show actual GPIO states."""
import time
import os
import sys

# Add picker to path
sys.path.insert(0, os.path.dirname(__file__))

from picker.config import DEFAULT_ROTARY_PIN_CLK, DEFAULT_ROTARY_PIN_DT

try:
    import RPi.GPIO as GPIO
    use_lgpio = False
except ImportError:
    try:
        import lgpio
        use_lgpio = True
    except ImportError:
        print("ERROR: Neither RPi.GPIO nor lgpio available")
        sys.exit(1)

# Setup from config
clk_pin = DEFAULT_ROTARY_PIN_CLK
dt_pin = DEFAULT_ROTARY_PIN_DT

print(f"Testing quadrature on CLK={clk_pin}, DT={dt_pin}")
print("Setup GPIO...")

if use_lgpio:
    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_input(h, clk_pin)
    lgpio.gpio_claim_input(h, dt_pin)
    gpio_read = lambda pin: lgpio.gpio_read(h, pin)
else:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup([clk_pin, dt_pin], GPIO.IN)
    gpio_read = lambda pin: GPIO.input(pin)

print("Reading GPIO state every 2ms for 10 seconds...")
print("Turn the knob during this time.\n")
print("Time(ms)  CLK DT  State  Raw")
print("-" * 35)

start = time.monotonic()
state_transitions = []
last_state = None

try:
    while time.monotonic() - start < 10:
        clk = gpio_read(clk_pin)
        dt = gpio_read(dt_pin)
        state = (clk << 1) | dt
        elapsed_ms = int((time.monotonic() - start) * 1000)
        
        state_str = f"{state:02b}"
        if state != last_state:
            state_transitions.append((elapsed_ms, last_state, state))
            last_state = state
            print(f"{elapsed_ms:5d}     {clk}  {dt}  {state_str}  ← CHANGE")
        else:
            print(f"{elapsed_ms:5d}     {clk}  {dt}  {state_str}")
        
        time.sleep(0.002)  # 2ms between reads
        
except KeyboardInterrupt:
    print("\nInterrupted!")

print("\n" + "=" * 40)
print("Detected state transitions:")
print(f"Total: {len(state_transitions)}")
for ms, old, new in state_transitions:
    print(f"  {ms:5d}ms: {old} -> {new}" if old is not None else f"  {ms:5d}ms: START at {new}")

# Cleanup
if use_lgpio:
    lgpio.gpiochip_close(h)
else:
    GPIO.cleanup()

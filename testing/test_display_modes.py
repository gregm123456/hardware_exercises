#!/usr/bin/env python3
"""Test different display modes and settings to isolate the banding issue."""

import sys
from pathlib import Path

# Ensure we can import the update_waveshare package
parent = str(Path(__file__).resolve().parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

from update_waveshare.core import display_image

def test_different_modes():
    """Test various display modes and settings."""
    
    tests = [
        # (description, mode, two_pass, dither, no_quant)
        ("Standard 4BPP GC16 only", "full", False, False, False),
        ("Standard 4BPP GC16 + dither", "full", False, True, False), 
        ("Standard 4BPP GC16 + two-pass", "full", True, False, False),
        ("Standard 4BPP GC16 + dither + two-pass", "full", True, True, False),
        ("8BPP GC16 only", "full", False, False, True),
        ("8BPP GC16 + two-pass", "full", True, False, True),
        ("8BPP GC16 + dither + two-pass", "full", True, True, True),
    ]
    
    print("Testing different display modes...")
    print("After each test, please report how the gradient looks.")
    print("Press ENTER to continue to next test, or 'q' to quit.")
    
    for i, (desc, mode, two_pass, dither, no_quant) in enumerate(tests):
        print(f"\n=== Test {i+1}: {desc} ===")
        
        try:
            regions = display_image(
                "gradient.png", 
                mode=mode, 
                two_pass=two_pass, 
                dither=dither, 
                no_quant=no_quant,
                vcom=-2.06
            )
            print(f"Updated regions: {regions}")
            print("How does the gradient look now?")
            
            response = input("Press ENTER for next test (or 'q' to quit): ").strip().lower()
            if response == 'q':
                break
                
        except Exception as e:
            print(f"Error in test: {e}")
            continue

if __name__ == "__main__":
    test_different_modes()

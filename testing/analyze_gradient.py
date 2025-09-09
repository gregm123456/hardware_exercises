#!/usr/bin/env python3
"""Analyze the original gradient.png to understand why it shows banding."""

from PIL import Image
import sys
from pathlib import Path

# Ensure we can import the update_waveshare package
parent = str(Path(__file__).resolve().parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

from update_waveshare.core import _load_and_prepare

def analyze_original_gradient():
    """Compare the original gradient.png with our test gradient."""
    
    print("=== ANALYZING ORIGINAL GRADIENT ===")
    
    # Load the original gradient
    original = Image.open("gradient.png").convert('L')
    print(f"Original gradient size: {original.size}")
    
    # Load our test gradient
    test = Image.open("test_full_gradient.png").convert('L')
    print(f"Test gradient size: {test.size}")
    
    # Compare a horizontal slice through the middle
    orig_width, orig_height = original.size
    test_width, test_height = test.size
    
    orig_middle = orig_height // 2
    test_middle = test_height // 2
    
    # Get pixel values across the width
    orig_slice = []
    for x in range(orig_width):
        orig_slice.append(original.getpixel((x, orig_middle)))
    
    test_slice = []
    for x in range(test_width):
        test_slice.append(test.getpixel((x, test_middle)))
    
    print(f"\nOriginal gradient:")
    print(f"  Range: {min(orig_slice)} to {max(orig_slice)}")
    print(f"  Unique values: {len(set(orig_slice))}")
    print(f"  First 20 values: {orig_slice[:20]}")
    print(f"  Last 20 values: {orig_slice[-20:]}")
    
    print(f"\nTest gradient:")
    print(f"  Range: {min(test_slice)} to {max(test_slice)}")
    print(f"  Unique values: {len(set(test_slice))}")
    print(f"  First 20 values: {test_slice[:20]}")
    print(f"  Last 20 values: {test_slice[-20:]}")
    
    # Check if the original has any unusual characteristics
    print(f"\n=== ANALYZING ORIGINAL GRADIENT CHARACTERISTICS ===")
    
    # Check for non-monotonic values (gradient should always increase)
    non_monotonic = False
    for i in range(1, len(orig_slice)):
        if orig_slice[i] < orig_slice[i-1]:
            print(f"Warning: Non-monotonic at position {i}: {orig_slice[i-1]} -> {orig_slice[i]}")
            non_monotonic = True
    
    if not non_monotonic:
        print("Original gradient is monotonic (good)")
    
    # Check for sudden jumps
    large_jumps = []
    for i in range(1, len(orig_slice)):
        diff = abs(orig_slice[i] - orig_slice[i-1])
        if diff > 5:  # Arbitrary threshold
            large_jumps.append((i, orig_slice[i-1], orig_slice[i], diff))
    
    if large_jumps:
        print(f"Found {len(large_jumps)} large jumps in original gradient:")
        for pos, prev_val, curr_val, diff in large_jumps[:10]:  # Show first 10
            print(f"  Position {pos}: {prev_val} -> {curr_val} (diff: {diff})")
    else:
        print("No large jumps found in original gradient")
    
    # Test processing both images with same parameters
    print(f"\n=== PROCESSING COMPARISON ===")
    target_size = (1448, 1072)
    
    # Process both with 4BPP dithering
    orig_processed = _load_and_prepare("gradient.png", target_size, target_bpp=4, dither=True, preview_out="debug_original_processed.png")
    test_processed = _load_and_prepare("test_full_gradient.png", target_size, target_bpp=4, dither=True, preview_out="debug_test_processed.png")
    
    # Get slices from processed images
    orig_proc_slice = []
    for x in range(target_size[0]):
        orig_proc_slice.append(orig_processed.getpixel((x, target_size[1] // 2)))
    
    test_proc_slice = []
    for x in range(target_size[0]):
        test_proc_slice.append(test_processed.getpixel((x, target_size[1] // 2)))
    
    print(f"Original processed unique values: {sorted(set(orig_proc_slice))}")
    print(f"Test processed unique values: {sorted(set(test_proc_slice))}")
    
    # Look for problematic quantization in original
    orig_levels = sorted(set(orig_proc_slice))
    test_levels = sorted(set(test_proc_slice))
    
    print(f"\nOriginal has {len(orig_levels)} quantization levels")
    print(f"Test has {len(test_levels)} quantization levels")
    
    if len(orig_levels) != len(test_levels):
        print("WARNING: Different number of quantization levels!")

if __name__ == "__main__":
    analyze_original_gradient()

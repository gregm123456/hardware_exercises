#!/usr/bin/env python3
"""Debug script to analyze gradient pixel values and packing behavior."""

import sys
from pathlib import Path
from PIL import Image

# Ensure we can import the update_waveshare package
parent = str(Path(__file__).resolve().parent)
if parent not in sys.path:
    sys.path.insert(0, parent)

from update_waveshare.core import _load_and_prepare

def analyze_gradient_processing():
    """Analyze how the gradient is processed through different quantization modes."""
    
    # Load and analyze the original gradient
    print("=== GRADIENT ANALYSIS ===")
    original = Image.open("gradient.png").convert('L')
    print(f"Original image size: {original.size}")
    
    # Get a horizontal slice through the middle to analyze the gradient
    width, height = original.size
    middle_row = height // 2
    slice_data = list(original.crop((0, middle_row, width, middle_row + 1)).getdata())
    
    print(f"Original gradient values (first 20 pixels): {slice_data[:20]}")
    print(f"Original gradient values (last 20 pixels): {slice_data[-20:]}")
    print(f"Range: {min(slice_data)} to {max(slice_data)}")
    print(f"Unique values in original: {len(set(slice_data))}")
    
    # Test different processing modes
    target_size = (1448, 1072)
    
    # Test 4BPP with dithering (what's used in full mode)
    print("\n=== 4BPP DITHERED (Full mode) ===")
    img_4bpp_dither = _load_and_prepare("gradient.png", target_size, target_bpp=4, dither=True, preview_out="debug_4bpp_dither.png")
    slice_4bpp_dither = list(img_4bpp_dither.crop((0, middle_row, width, middle_row + 1)).getdata())
    print(f"4BPP dithered unique values: {sorted(set(slice_4bpp_dither))}")
    print(f"4BPP dithered range: {min(slice_4bpp_dither)} to {max(slice_4bpp_dither)}")
    
    # Test 8BPP (what's used with --no-quant)
    print("\n=== 8BPP (No quantization) ===")
    img_8bpp = _load_and_prepare("gradient.png", target_size, target_bpp=8, dither=False, preview_out="debug_8bpp.png")
    slice_8bpp = list(img_8bpp.crop((0, middle_row, width, middle_row + 1)).getdata())
    print(f"8BPP unique values: {len(set(slice_8bpp))}")
    print(f"8BPP range: {min(slice_8bpp)} to {max(slice_8bpp)}")
    
    # Analyze pixel packing behavior
    print("\n=== PIXEL PACKING ANALYSIS ===")
    
    # Simulate 4BPP packing (what happens in SPI code)
    print("4BPP packing simulation:")
    for i in range(0, min(20, len(slice_4bpp_dither))):
        original_val = slice_4bpp_dither[i]
        packed_val = original_val >> 4  # Top 4 bits (what SPI code does)
        unpacked_val = packed_val << 4  # What display hardware sees
        print(f"  Pixel {i}: {original_val:3d} -> packed {packed_val:2d} -> unpacked {unpacked_val:3d}")
    
    # Check for potential issues in 4BPP quantization
    quantized_levels = sorted(set(slice_4bpp_dither))
    print(f"\n4BPP quantized levels: {quantized_levels}")
    
    # Look for problematic level transitions
    print("\nChecking for problematic level transitions:")
    for i in range(len(quantized_levels) - 1):
        curr_level = quantized_levels[i]
        next_level = quantized_levels[i + 1]
        gap = next_level - curr_level
        packed_curr = curr_level >> 4
        packed_next = next_level >> 4
        if packed_curr == packed_next:
            print(f"  WARNING: Levels {curr_level} and {next_level} both pack to {packed_curr}")
        elif gap > 20:
            print(f"  Large gap: {curr_level} to {next_level} (gap: {gap})")

if __name__ == "__main__":
    analyze_gradient_processing()

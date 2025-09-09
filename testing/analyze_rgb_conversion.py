#!/usr/bin/env python3
"""Analyze RGB vs grayscale conversion issues."""

from PIL import Image

def analyze_rgb_conversion():
    """Analyze how RGB conversion might cause issues."""
    
    print("=== RGB CONVERSION ANALYSIS ===")
    
    # Load original as-is
    original_rgb = Image.open("gradient.png")
    print(f"Original mode: {original_rgb.mode}")
    print(f"Original size: {original_rgb.size}")
    
    # Convert to grayscale and save
    original_gray = original_rgb.convert('L')
    original_gray.save("gradient_converted_to_gray.png")
    print("Saved gradient_converted_to_gray.png")
    
    # Load our test gradient
    test_gray = Image.open("test_diagonal_gradient.png")
    
    # Compare a diagonal slice from both
    width, height = original_rgb.size
    
    # Get diagonal samples (every 10th pixel along the diagonal)
    diagonal_samples_rgb = []
    diagonal_samples_converted = []
    
    for i in range(0, min(width, height), 10):
        # RGB values
        r, g, b = original_rgb.getpixel((i, i))
        diagonal_samples_rgb.append((r, g, b))
        
        # Converted grayscale value
        gray_val = original_gray.getpixel((i, i))
        diagonal_samples_converted.append(gray_val)
    
    print(f"\nFirst 10 diagonal RGB samples: {diagonal_samples_rgb[:10]}")
    print(f"First 10 converted gray values: {diagonal_samples_converted[:10]}")
    
    # Check if RGB channels are equal (should be for a proper grayscale)
    non_gray_pixels = 0
    for y in range(height):
        for x in range(width):
            r, g, b = original_rgb.getpixel((x, y))
            if not (r == g == b):
                non_gray_pixels += 1
                if non_gray_pixels <= 5:  # Show first 5 examples
                    print(f"Non-gray pixel at ({x},{y}): RGB({r},{g},{b})")
    
    if non_gray_pixels > 0:
        print(f"WARNING: Found {non_gray_pixels} non-gray pixels in 'grayscale' image!")
    else:
        print("All pixels are pure grayscale (R=G=B)")
    
    # Check color space/gamma issues
    print(f"\nColor profile info:")
    if hasattr(original_rgb, 'info'):
        for key, value in original_rgb.info.items():
            if 'gamma' in key.lower() or 'color' in key.lower() or 'icc' in key.lower():
                print(f"  {key}: {value}")

if __name__ == "__main__":
    analyze_rgb_conversion()

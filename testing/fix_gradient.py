#!/usr/bin/env python3
"""Fix the original gradient to use full dynamic range."""

from PIL import Image

def fix_original_gradient():
    """Stretch the original gradient to use full 0-255 range."""
    
    # Load the original
    original = Image.open("gradient.png").convert('L')
    
    # Get the current range
    pixels = list(original.getdata())
    min_val = min(pixels)
    max_val = max(pixels)
    
    print(f"Original range: {min_val} to {max_val}")
    
    # Create a new image with stretched range
    width, height = original.size
    fixed = Image.new('L', (width, height))
    
    for y in range(height):
        for x in range(width):
            old_val = original.getpixel((x, y))
            # Stretch from old range to 0-255
            new_val = int(255 * (old_val - min_val) / (max_val - min_val))
            fixed.putpixel((x, y), new_val)
    
    fixed.save("gradient_fixed.png")
    print(f"Created gradient_fixed.png with full 0-255 range")
    
    # Verify the fix
    fixed_pixels = list(fixed.getdata())
    print(f"Fixed range: {min(fixed_pixels)} to {max(fixed_pixels)}")

if __name__ == "__main__":
    fix_original_gradient()

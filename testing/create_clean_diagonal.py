#!/usr/bin/env python3
"""Create a clean diagonal gradient that should work perfectly."""

from PIL import Image
import math

def create_clean_diagonal():
    """Create a clean diagonal gradient optimized for e-paper display."""
    
    width, height = 1448, 1072
    
    # Create a diagonal gradient that's optimized for 16-level quantization
    # We'll use values that map cleanly to the 16 quantization levels
    img = Image.new('L', (width, height), 255)
    
    # Calculate diagonal distance
    max_distance = math.sqrt(width**2 + height**2)
    
    # Pre-calculate the 16 quantization levels (what 4BPP dithering targets)
    # These are the levels that work well: 0, 17, 34, 51, 68, 85, 102, 119, 136, 153, 170, 187, 204, 221, 238, 255
    target_levels = [i * 17 for i in range(16)]  # 0, 17, 34, ..., 255
    
    for y in range(height):
        for x in range(width):
            # Distance from top-left corner
            distance = math.sqrt(x**2 + y**2)
            # Map distance to 0-15 range, then to target levels
            level_index = int(15 * distance / max_distance)
            gray_value = target_levels[level_index]
            img.putpixel((x, y), gray_value)
    
    img.save("clean_diagonal_gradient.png")
    print("Created clean_diagonal_gradient.png - optimized for 16-level quantization")
    
    # Also create a version that uses exact display levels
    img2 = Image.new('L', (width, height), 255)
    
    # Use the exact levels we found in our analysis that work well
    display_levels = [7, 23, 38, 54, 70, 85, 102, 118, 134, 149, 166, 182, 198, 213, 229, 246]
    
    for y in range(height):
        for x in range(width):
            distance = math.sqrt(x**2 + y**2)
            level_index = int((len(display_levels) - 1) * distance / max_distance)
            gray_value = display_levels[level_index]
            img2.putpixel((x, y), gray_value)
    
    img2.save("optimal_diagonal_gradient.png")
    print("Created optimal_diagonal_gradient.png - using tested display levels")

if __name__ == "__main__":
    create_clean_diagonal()

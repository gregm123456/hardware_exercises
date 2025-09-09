#!/usr/bin/env python3
"""Create a full black-to-white gradient test image."""

from PIL import Image

def create_full_gradient():
    """Create a smooth full black-to-white gradient."""
    
    width, height = 1448, 1072
    
    # Create horizontal gradient from pure black (0) to pure white (255)
    img = Image.new('L', (width, height), 255)
    
    for x in range(width):
        # Map x position to gray value from 0 to 255
        gray_value = int(255 * x / (width - 1))
        
        for y in range(height):
            img.putpixel((x, y), gray_value)
    
    img.save("test_full_gradient.png")
    print(f"Created test_full_gradient.png - smooth gradient from black (0) to white (255)")
    
    # Also create a version with more precise control
    # Let's make sure we hit exact values including the problematic ones we identified
    img2 = Image.new('L', (width, height), 255)
    
    for x in range(width):
        # Use floating point for more precision
        gray_value = int(255.0 * x / (width - 1))
        
        for y in range(height):
            img2.putpixel((x, y), gray_value)
    
    img2.save("test_precise_gradient.png")
    print(f"Created test_precise_gradient.png - precise floating-point gradient")

if __name__ == "__main__":
    create_full_gradient()

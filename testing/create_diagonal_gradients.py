#!/usr/bin/env python3
"""Create diagonal gradient test images to reproduce the banding issue."""

from PIL import Image
import math

def create_diagonal_gradients():
    """Create diagonal gradient test images."""
    
    width, height = 1448, 1072
    
    # Diagonal gradient from top-left (black) to bottom-right (white)
    img1 = Image.new('L', (width, height), 255)
    
    # Calculate the maximum diagonal distance
    max_distance = math.sqrt(width**2 + height**2)
    
    for y in range(height):
        for x in range(width):
            # Distance from top-left corner
            distance = math.sqrt(x**2 + y**2)
            # Map distance to gray value 0-255
            gray_value = int(255 * distance / max_distance)
            img1.putpixel((x, y), gray_value)
    
    img1.save("test_diagonal_gradient.png")
    print("Created test_diagonal_gradient.png - diagonal from top-left to bottom-right")
    
    # Also create the reverse diagonal (top-right to bottom-left)
    img2 = Image.new('L', (width, height), 255)
    
    for y in range(height):
        for x in range(width):
            # Distance from top-right corner
            distance = math.sqrt((width - x)**2 + y**2)
            # Map distance to gray value 0-255
            gray_value = int(255 * distance / max_distance)
            img2.putpixel((x, y), gray_value)
    
    img2.save("test_diagonal_gradient_reverse.png")
    print("Created test_diagonal_gradient_reverse.png - diagonal from top-right to bottom-left")
    
    # And create a radial gradient from center
    img3 = Image.new('L', (width, height), 255)
    center_x, center_y = width // 2, height // 2
    max_radius = math.sqrt(center_x**2 + center_y**2)
    
    for y in range(height):
        for x in range(width):
            # Distance from center
            distance = math.sqrt((x - center_x)**2 + (y - center_y)**2)
            # Map distance to gray value 0-255
            gray_value = int(255 * distance / max_radius)
            img3.putpixel((x, y), gray_value)
    
    img3.save("test_radial_gradient.png")
    print("Created test_radial_gradient.png - radial from center outward")

if __name__ == "__main__":
    create_diagonal_gradients()

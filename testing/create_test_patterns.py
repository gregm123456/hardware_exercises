#!/usr/bin/env python3
"""Create a simple test pattern to isolate the banding issue."""

from PIL import Image

def create_test_patterns():
    """Create simple test patterns to isolate the issue."""
    
    # Create a simple 16-step test pattern
    width, height = 1448, 1072
    
    # Pattern 1: 16 vertical bands of equal width
    img1 = Image.new('L', (width, height), 255)
    band_width = width // 16
    
    for i in range(16):
        gray_value = i * 17  # 0, 17, 34, 51, ..., 255
        x_start = i * band_width
        x_end = min((i + 1) * band_width, width)
        
        for x in range(x_start, x_end):
            for y in range(height):
                img1.putpixel((x, y), gray_value)
    
    img1.save("test_16_bands.png")
    print("Created test_16_bands.png - 16 equal gray steps")
    
    # Pattern 2: Just the problematic range
    img2 = Image.new('L', (width, height), 255)
    
    # Focus on the range where we saw the issue (around values 64-78)
    test_values = [48, 56, 64, 72, 78, 86, 94, 102]  # 8 values around the problem area
    band_width = width // len(test_values)
    
    for i, gray_value in enumerate(test_values):
        x_start = i * band_width
        x_end = min((i + 1) * band_width, width)
        
        for x in range(x_start, x_end):
            for y in range(height):
                img2.putpixel((x, y), gray_value)
    
    img2.save("test_problem_range.png")
    print("Created test_problem_range.png - focused on problematic gray range")
    
    # Pattern 3: Smooth gradient in the problem range only
    img3 = Image.new('L', (width, height), 255)
    
    for x in range(width):
        # Map x position to gray value in the problem range
        gray_value = int(48 + (102 - 48) * x / width)  # Smooth from 48 to 102
        
        for y in range(height):
            img3.putpixel((x, y), gray_value)
    
    img3.save("test_smooth_problem_range.png")
    print("Created test_smooth_problem_range.png - smooth gradient in problem range")

if __name__ == "__main__":
    create_test_patterns()

"""Tests for gamma adjustment functionality in sd_client."""
import os
import tempfile
from PIL import Image
from picker.sd_client import _apply_gamma


def test_gamma_no_change():
    """Test that gamma=1.0 returns unchanged image."""
    # Create a simple test image with gradient
    img = Image.new('L', (100, 100))
    pixels = img.load()
    for x in range(100):
        for y in range(100):
            pixels[x, y] = x * 255 // 99  # gradient from 0 to 255
    
    result = _apply_gamma(img, 1.0)
    
    # Should be identical
    assert result.getpixel((0, 0)) == img.getpixel((0, 0))
    assert result.getpixel((50, 50)) == img.getpixel((50, 50))
    assert result.getpixel((99, 99)) == img.getpixel((99, 99))


def test_gamma_brightens_midtones():
    """Test that gamma>1.0 brightens midtones while preserving endpoints."""
    img = Image.new('L', (256, 1))
    pixels = img.load()
    for x in range(256):
        pixels[x, 0] = x
    
    result = _apply_gamma(img, 1.6)
    
    # Black (0) should stay black
    assert result.getpixel((0, 0)) == 0
    
    # White (255) should stay white
    assert result.getpixel((255, 0)) == 255
    
    # Midtones should be brightened
    # 128 with gamma 1.6 should become ~170
    mid_original = 128
    mid_result = result.getpixel((mid_original, 0))
    assert mid_result > mid_original, f"Midtone should be brightened: {mid_result} > {mid_original}"
    assert mid_result < 255, "Midtone should not reach white"
    
    # Lower midtone (64) should also be brightened
    low_mid_original = 64
    low_mid_result = result.getpixel((low_mid_original, 0))
    assert low_mid_result > low_mid_original


def test_gamma_preserves_full_range():
    """Test that gamma adjustment preserves full dynamic range 0-255."""
    # Create image with full range of values
    img = Image.new('L', (256, 1))
    pixels = img.load()
    for x in range(256):
        pixels[x, 0] = x
    
    result = _apply_gamma(img, 1.8)
    
    # Get all unique pixel values
    result_pixels = [result.getpixel((x, 0)) for x in range(256)]
    
    # Should have black (0) and white (255)
    assert min(result_pixels) == 0, "Should preserve black"
    assert max(result_pixels) == 255, "Should preserve white"
    
    # Should have a range of values (not just binary)
    unique_values = len(set(result_pixels))
    assert unique_values > 100, f"Should have many distinct values, got {unique_values}"


def test_gamma_rgb_mode():
    """Test gamma adjustment works on RGB images."""
    img = Image.new('RGB', (100, 100), (128, 128, 128))
    
    result = _apply_gamma(img, 1.6)
    
    assert result.mode == 'RGB'
    # All channels should be brightened equally
    r, g, b = result.getpixel((50, 50))
    assert r == g == b
    assert r > 128, "Gray should be brightened"


def test_gamma_calculation_accuracy():
    """Test that gamma calculation matches expected formula."""
    img = Image.new('L', (1, 1), 128)
    
    # For input=128, gamma=1.6:
    # output = 255 * (128/255)^(1/1.6) = 255 * 0.502^0.625 ≈ 169
    result = _apply_gamma(img, 1.6)
    result_value = result.getpixel((0, 0))
    
    # Check within reasonable tolerance
    expected = int(255 * ((128 / 255.0) ** (1.0 / 1.6)))
    assert abs(result_value - expected) <= 1, f"Expected ~{expected}, got {result_value}"


def test_gamma_below_one_darkens():
    """Test that gamma<1.0 darkens midtones."""
    img = Image.new('L', (1, 1), 128)
    
    result = _apply_gamma(img, 0.5)
    result_value = result.getpixel((0, 0))
    
    assert result_value < 128, f"Should darken: {result_value} < 128"


if __name__ == "__main__":
    test_gamma_no_change()
    test_gamma_brightens_midtones()
    test_gamma_preserves_full_range()
    test_gamma_rgb_mode()
    test_gamma_calculation_accuracy()
    test_gamma_below_one_darkens()
    print("All gamma tests passed!")

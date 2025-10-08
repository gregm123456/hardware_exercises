"""Integration tests for gamma adjustment in the image generation pipeline."""
import os
import tempfile
from PIL import Image
from unittest.mock import patch, MagicMock
import base64
from io import BytesIO

# Mock the sd_config to avoid needing actual config
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from picker import sd_client, sd_config


def test_generate_image_applies_default_gamma():
    """Test that generate_image applies default gamma from config."""
    # Create a mock response with a test image
    test_img = Image.new('RGB', (512, 512), (128, 128, 128))
    buffer = BytesIO()
    test_img.save(buffer, format='PNG')
    img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    mock_response = {'images': [img_b64]}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, 'test_output.png')
        
        # Mock the API call
        with patch.object(sd_client, '_call_api', return_value=mock_response):
            result_path = sd_client.generate_image(
                "test prompt",
                output_path=output_path,
                overrides={'width': 512, 'height': 512}
            )
        
        # Verify output was created
        assert os.path.exists(result_path)
        
        # Load the result and verify it was gamma-adjusted
        result_img = Image.open(result_path)
        result_pixel = result_img.getpixel((256, 256))
        
        # Original was (128, 128, 128), with gamma 1.6 it should be brighter
        # Expected: ~169 for each channel
        r, g, b = result_pixel
        assert r > 128, f"Red channel should be brightened: {r} > 128"
        assert g > 128, f"Green channel should be brightened: {g} > 128"
        assert b > 128, f"Blue channel should be brightened: {b} > 128"


def test_generate_image_respects_gamma_override():
    """Test that generate_image respects gamma value in overrides."""
    # Create a mock response with a test image
    test_img = Image.new('RGB', (512, 512), (128, 128, 128))
    buffer = BytesIO()
    test_img.save(buffer, format='PNG')
    img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    mock_response = {'images': [img_b64]}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, 'test_output.png')
        
        # Mock the API call and specify gamma=1.0 (no adjustment)
        with patch.object(sd_client, '_call_api', return_value=mock_response):
            result_path = sd_client.generate_image(
                "test prompt",
                output_path=output_path,
                overrides={'width': 512, 'height': 512, 'gamma': 1.0}
            )
        
        # Verify output was created
        assert os.path.exists(result_path)
        
        # Load the result and verify it was NOT gamma-adjusted
        result_img = Image.open(result_path)
        result_pixel = result_img.getpixel((256, 256))
        
        # With gamma=1.0, should be unchanged
        r, g, b = result_pixel
        # Allow small tolerance for JPEG artifacts or rounding
        assert abs(r - 128) <= 2, f"Red channel should be ~128: {r}"
        assert abs(g - 128) <= 2, f"Green channel should be ~128: {g}"
        assert abs(b - 128) <= 2, f"Blue channel should be ~128: {b}"


def test_generate_image_with_extreme_gamma():
    """Test that generate_image handles extreme gamma values."""
    # Create a mock response with a test image with gradient
    test_img = Image.new('RGB', (512, 512))
    pixels = test_img.load()
    for x in range(512):
        for y in range(512):
            gray = x * 255 // 511
            pixels[x, y] = (gray, gray, gray)
    
    buffer = BytesIO()
    test_img.save(buffer, format='PNG')
    img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    mock_response = {'images': [img_b64]}
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, 'test_output.png')
        
        # Test with high gamma
        with patch.object(sd_client, '_call_api', return_value=mock_response):
            result_path = sd_client.generate_image(
                "test prompt",
                output_path=output_path,
                overrides={'width': 512, 'height': 512, 'gamma': 2.0}
            )
        
        # Verify output was created and has valid range
        assert os.path.exists(result_path)
        result_img = Image.open(result_path)
        
        # Check endpoints are preserved
        assert result_img.getpixel((0, 0))[0] == 0, "Black should be preserved"
        assert result_img.getpixel((511, 0))[0] == 255, "White should be preserved"


def test_config_has_epaper_gamma():
    """Test that sd_config defines EPAPER_GAMMA."""
    assert hasattr(sd_config, 'EPAPER_GAMMA'), "sd_config should define EPAPER_GAMMA"
    gamma = sd_config.EPAPER_GAMMA
    assert isinstance(gamma, (int, float)), "EPAPER_GAMMA should be numeric"
    assert gamma > 0, "EPAPER_GAMMA should be positive"
    assert gamma <= 3.0, "EPAPER_GAMMA should be reasonable (<=3.0)"


if __name__ == "__main__":
    test_generate_image_applies_default_gamma()
    test_generate_image_respects_gamma_override()
    test_generate_image_with_extreme_gamma()
    test_config_has_epaper_gamma()
    print("All integration tests passed!")

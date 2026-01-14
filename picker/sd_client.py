import json
import urllib.request
import base64
import os
import time
import logging
from datetime import datetime
from typing import Optional

from PIL import Image
from io import BytesIO

import picker.sd_config as sd_config

logger = logging.getLogger(__name__)


def _timestamp():
    return datetime.fromtimestamp(time.time()).strftime("%Y%m%d-%H%M%S")


def _apply_gamma(img: Image.Image, gamma: float) -> Image.Image:
    """Apply gamma correction to brighten midtones while preserving full dynamic range.
    
    Args:
        img: PIL Image in RGB or L mode
        gamma: Gamma value (>1.0 brightens, <1.0 darkens, 1.0 = no change)
    
    Returns:
        Gamma-corrected PIL Image in the same mode as input
    """
    if gamma == 1.0:
        return img
    
    # Build a lookup table mapping input values 0-255 to output values 0-255
    # Formula: output = 255 * (input/255)^(1/gamma)
    inv_gamma = 1.0 / gamma
    lut = [int(255 * ((i / 255.0) ** inv_gamma)) for i in range(256)]
    
    # Apply the lookup table to the image
    # For RGB images, apply to all channels
    if img.mode == 'RGB':
        return img.point(lambda x: lut[x])
    elif img.mode == 'L':
        return img.point(lut)
    else:
        # For other modes, convert to RGB, apply gamma, convert back
        orig_mode = img.mode
        img_rgb = img.convert('RGB')
        img_corrected = img_rgb.point(lambda x: lut[x])
        return img_corrected.convert(orig_mode)


def _call_api(endpoint: str, payload: dict, base_url: Optional[str] = None) -> dict:
    url = (base_url or sd_config.SD_IMAGE_WEBUI_SERVER_URL).rstrip('/') + '/' + endpoint.lstrip('/')
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def generate_image(prompt: str, output_path: Optional[str] = None, overrides: dict = None, mode: str = 'txt2img', init_image: Optional[str] = None) -> str:
    """Generate an image via SD Web UI txt2img and save the first result as a PNG.

    Returns the path to the saved PNG. Raises exceptions on network/API errors.
    """
    output_path = output_path or sd_config.DEFAULT_OUTPUT_PATH
    overrides = overrides or {}

    payload = {
        "prompt": prompt,
        "negative_prompt": sd_config.NEGATIVE_IMAGE_PROMPT,
        "seed": -1,
        "steps": overrides.get('steps', sd_config.SD_STEPS),
        "width": overrides.get('width', sd_config.SD_WIDTH),
        "height": overrides.get('height', sd_config.SD_HEIGHT),
        "cfg_scale": overrides.get('cfg_scale', sd_config.SD_CFG_SCALE),
        "sampler_name": overrides.get('sampler_name', sd_config.SD_SAMPLER_NAME),
        "denoising_strength": overrides.get('denoising_strength', getattr(sd_config, 'SD_DENOISING_STRENGTH', 0.75)),
        "n_iter": overrides.get('n_iter', sd_config.SD_N_ITER),
        "batch_size": overrides.get('batch_size', sd_config.SD_BATCH_SIZE),
    }

    if mode == 'img2img' and init_image:
        payload["mode"] = "img2img"
        payload["init_image"] = init_image
        # Try both formats (some proxies expect plural list)
        payload["init_images"] = [init_image]
        endpoint = 'generate'
        logger.info(f"Using img2img mode (init_image length: {len(init_image)})")
    else:
        payload["mode"] = "txt2img"
        endpoint = 'generate'
        logger.info("Using txt2img mode")

    # Log endpoint and safe payload metadata (don't dump large base64 strings)
    logger.debug(f"Calling API endpoint: {endpoint}")
    try:
        init_len = len(payload.get('init_image')) if payload.get('init_image') else 0
    except Exception:
        init_len = 0
    logger.debug(f"Payload keys: {list(payload.keys())}; init_image_length={init_len}")

    resp = _call_api(endpoint, payload)
    logger.debug(f"API response keys: {list(resp.keys())}")
    # If the backend returns a single base64 image, don't log the full string; log its length instead
    if resp.get('image'):
        try:
            logger.debug(f"Response single 'image' length: {len(resp.get('image'))}")
        except Exception:
            logger.debug("Response single 'image' present (length unknown)")
    if resp.get('base64'):
        try:
            logger.debug(f"Response single 'base64' length: {len(resp.get('base64'))}")
        except Exception:
            logger.debug("Response single 'base64' present (length unknown)")
    if isinstance(resp.get('images'), list):
        try:
            lengths = [len(x) if isinstance(x, str) else 0 for x in resp.get('images')]
            logger.debug(f"Response 'images' lengths: {lengths}")
        except Exception:
            logger.debug("Response 'images' present but lengths unavailable")
    # Support backends that return either an 'images' list (standard) or a
    # single 'image' field with a base64 string. Normalize to a list.
    images = []
    if isinstance(resp.get('images'), list) and resp.get('images'):
        images = resp.get('images')
    elif resp.get('image'):
        # Some backends return the single image as 'image' (base64 string)
        images = [resp.get('image')]
    elif resp.get('base64'):
        # Some backends return the single image as 'base64' (base64 string)
        images = [resp.get('base64')]

    if not images:
        logger.error(f"No images in response. Response: {resp}")
        raise RuntimeError('No images returned from SD API')

    # Use first image; decode base64 and save as PNG using Pillow to ensure proper
    # conversion and resizing if needed.
    img_b64 = images[0]
    img_data = base64.b64decode(img_b64)
    img = Image.open(BytesIO(img_data)).convert('RGB')

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    # Resize to target dimensions if different (ensures 512x512 main image)
    try:
        target_w = overrides.get('width', sd_config.SD_WIDTH)
        target_h = overrides.get('height', sd_config.SD_HEIGHT)
        if img.size != (target_w, target_h):
            img = img.resize((target_w, target_h), Image.LANCZOS)
    except Exception:
        # ignore resizing errors and save original
        pass

    # Apply gamma correction for e-paper display brightness
    # This brightens midtones while preserving full dynamic range
    try:
        gamma = overrides.get('gamma', sd_config.EPAPER_GAMMA)
        if gamma != 1.0:
            img = _apply_gamma(img, gamma)
    except Exception:
        # ignore gamma adjustment errors and save original
        pass

    # Save as PNG (atomic write)
    tmp_path = f"{output_path}.{_timestamp()}.tmp"
    img.save(tmp_path, format='PNG')
    os.replace(tmp_path, output_path)
    return output_path


def interrogate_structured(image_b64: str, categories: dict) -> dict:
    """Perform structured interrogation on a base64-encoded image.

    Args:
        image_b64: The base64-encoded image string.
        categories: A dictionary of categories and their possible values.
                    e.g. {"hair_color": ["pink", "blonde", "brown", "black"]}

    Returns:
        The JSON response from the interrogation API.
    """
    payload = {
        "image": image_b64,
        "categories": categories
    }
    
    endpoint = "/sdapi/v1/interrogate/structured"
    logger.info(f"Calling structured interrogation API for {len(categories)} categories")
    
    try:
        resp = _call_api(endpoint, payload)
        return resp
    except Exception as e:
        logger.error(f"Structured interrogation failed: {e}")
        return {"error": str(e), "results": {}, "general_tags": []}

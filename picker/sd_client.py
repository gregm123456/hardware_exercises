import json
import urllib.request
import base64
import os
import time
from datetime import datetime
from typing import Optional

from PIL import Image
from io import BytesIO

import picker.sd_config as sd_config


def _timestamp():
    return datetime.fromtimestamp(time.time()).strftime("%Y%m%d-%H%M%S")


def _call_api(endpoint: str, payload: dict, base_url: Optional[str] = None) -> dict:
    url = (base_url or sd_config.SD_IMAGE_WEBUI_SERVER_URL).rstrip('/') + '/' + endpoint.lstrip('/')
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def generate_image(prompt: str, output_path: Optional[str] = None, overrides: dict = None) -> str:
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
        "n_iter": overrides.get('n_iter', sd_config.SD_N_ITER),
        "batch_size": overrides.get('batch_size', sd_config.SD_BATCH_SIZE),
    }

    resp = _call_api('sdapi/v1/txt2img', payload)
    images = resp.get('images') or []
    if not images:
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

    # Save as PNG (atomic write)
    tmp_path = f"{output_path}.{_timestamp()}.tmp"
    img.save(tmp_path, format='PNG')
    os.replace(tmp_path, output_path)
    return output_path

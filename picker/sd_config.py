"""Stable Diffusion client configuration used by the picker GO action.

This module exposes constants that control how prompts are constructed and
how the SD Web UI API is called. Values here are intentionally conservative
defaults; operators may override them per-deployment.
"""
from typing import List
from pathlib import Path

# Prompt framing
# IMAGE_PROMPT_PREFIX = "(((pencil drawing sketch))), face portrait, <lora:suxierenV1:.5>, criminal mug shot, "
IMAGE_PROMPT_PREFIX = "photograph, face portrait, "
IMAGE_PROMPT_SUFFIX = ""
NEGATIVE_IMAGE_PROMPT = ", bad anatomy, watermark, text"

# SD Web UI server URL (no trailing slash)
SD_IMAGE_WEBUI_SERVER_URL = "http://192.168.4.108:7860"

# Stable Diffusion generation parameters (defaults)
SD_STEPS = 7
SD_WIDTH = 512
SD_HEIGHT = 512
SD_CFG_SCALE = 1.5
SD_SAMPLER_NAME = "DPM++ 2M Karras"
SD_N_ITER = 1
SD_BATCH_SIZE = 1

# Additional allowed extras that may be populated by the caller
EXTRA_PROMPT_TAGS: List[str] = []

DEFAULT_OUTPUT_PATH = str(Path(__file__).parent / 'assets' / 'placeholder.png')

"""Generates image suggestions via OpenAI (gpt-image-1) and hosts them on ImgBB,
since Ocoya only accepts publicly reachable media URLs, not raw file uploads."""
import base64
import os
from typing import List

import requests

OPENAI_URL = "https://api.openai.com/v1/images/generations"
IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"
IMAGE_MODEL = "gpt-image-1"
IMAGE_SIZE = "1024x1024"


def _generate_image_bytes(prompt: str) -> bytes:
    response = requests.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": IMAGE_MODEL, "prompt": prompt, "size": IMAGE_SIZE, "n": 1},
        timeout=120,
    )
    response.raise_for_status()
    return base64.b64decode(response.json()["data"][0]["b64_json"])


def upload_to_imgbb(image_bytes: bytes) -> str:
    """Uploads raw image bytes to ImgBB and returns the public URL."""
    response = requests.post(
        IMGBB_UPLOAD_URL,
        params={"key": os.environ["IMGBB_API_KEY"]},
        data={"image": base64.b64encode(image_bytes).decode("ascii")},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"ImgBB-Upload fehlgeschlagen: {data}")
    return data["data"]["url"]


def generate_image_suggestions(prompts: List[str]) -> List[str]:
    """Generates one image per prompt via OpenAI and returns public ImgBB URLs."""
    return [upload_to_imgbb(_generate_image_bytes(prompt)) for prompt in prompts]

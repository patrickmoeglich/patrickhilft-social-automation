"""Generates image suggestions via OpenAI (gpt-image-1) and hosts them on Imgur,
since Ocoya only accepts publicly reachable media URLs, not raw file uploads."""
import base64
import os
from typing import List

import requests

OPENAI_URL = "https://api.openai.com/v1/images/generations"
IMGUR_UPLOAD_URL = "https://api.imgur.com/3/image"
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


def upload_to_imgur(image_bytes: bytes) -> str:
    """Uploads raw image bytes to Imgur (anonymous) and returns the public URL."""
    response = requests.post(
        IMGUR_UPLOAD_URL,
        headers={"Authorization": f"Client-ID {os.environ['IMGUR_CLIENT_ID']}"},
        data={"image": base64.b64encode(image_bytes).decode("ascii"), "type": "base64"},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"Imgur-Upload fehlgeschlagen: {data}")
    return data["data"]["link"]


def generate_image_suggestions(prompts: List[str]) -> List[str]:
    """Generates one image per prompt via OpenAI and returns public Imgur URLs."""
    return [upload_to_imgur(_generate_image_bytes(prompt)) for prompt in prompts]

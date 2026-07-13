"""Generates images via OpenAI (gpt-image-1) and hosts them on Cloudinary."""
import base64
import os
import time
from typing import List

import requests

import cloudinary_client

OPENAI_URL = "https://api.openai.com/v1/images/generations"
IMAGE_MODEL = "gpt-image-1"
IMAGE_SIZE = "1024x1024"
MAX_RETRIES = 3
ERROR_BODY_LIMIT = 500


def _generate_image_bytes(prompt: str) -> bytes:
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={"model": IMAGE_MODEL, "prompt": prompt, "size": IMAGE_SIZE, "n": 1},
            timeout=120,
        )
        if response.ok:
            return base64.b64decode(response.json()["data"][0]["b64_json"])
        # 5xx errors are usually transient (e.g. upstream gateway issues) - retry with backoff.
        if response.status_code >= 500 and attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(
            f"OpenAI-Bildgenerierung fehlgeschlagen ({response.status_code}): "
            f"{response.text[:ERROR_BODY_LIMIT]}"
        )


def generate_images(prompts: List[str]) -> List[bytes]:
    """Generates one raw image per prompt via OpenAI."""
    return [_generate_image_bytes(prompt) for prompt in prompts]


def generate_and_host_images(prompts: List[str]) -> List[dict]:
    """Generates images and uploads them to Cloudinary.

    Returns a list of {"bytes": raw image bytes, "url": public Cloudinary URL},
    keeping the raw bytes around too since video_gen.py renders locally from
    them rather than re-downloading from Cloudinary.
    """
    results = []
    for i, image_bytes in enumerate(generate_images(prompts)):
        url = cloudinary_client.upload(image_bytes, resource_type="image", filename=f"daily_{i}.png")
        results.append({"bytes": image_bytes, "url": url})
    return results

"""Generates image suggestions via OpenAI (gpt-image-1) and hosts them on ImgBB,
since Ocoya only accepts publicly reachable media URLs, not raw file uploads."""
import base64
import os
import time
from typing import List

import requests

OPENAI_URL = "https://api.openai.com/v1/images/generations"
IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"
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


def upload_to_imgbb(image_bytes: bytes) -> str:
    """Uploads raw image bytes to ImgBB and returns the public URL."""
    response = requests.post(
        IMGBB_UPLOAD_URL,
        params={"key": os.environ["IMGBB_API_KEY"]},
        data={"image": base64.b64encode(image_bytes).decode("ascii")},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"ImgBB-Upload fehlgeschlagen ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}")
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"ImgBB-Upload fehlgeschlagen: {data}")
    return data["data"]["url"]


def generate_image_suggestions(prompts: List[str]) -> List[str]:
    """Generates one image per prompt via OpenAI and returns public ImgBB URLs."""
    return [upload_to_imgbb(_generate_image_bytes(prompt)) for prompt in prompts]

"""Minimal Cloudinary upload client (signed upload, no SDK dependency).

Used to host both images and videos at a public HTTPS URL, since Instagram/
TikTok/LinkedIn/X all require either a public URL or a direct binary upload -
Cloudinary's free tier covers both media types with one API, unlike ImgBB
(images only) which the existing weekly workflow uses.
"""
import hashlib
import os
import time
from typing import Optional

import requests

ERROR_BODY_LIMIT = 500


def _signature(params: dict, api_secret: str) -> str:
    to_sign = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.sha1((to_sign + api_secret).encode("utf-8")).hexdigest()


def upload(file_bytes: bytes, resource_type: str, filename: str) -> str:
    """Uploads raw bytes to Cloudinary and returns the public `secure_url`.

    resource_type: "image" or "video".
    """
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"]
    api_key = os.environ["CLOUDINARY_API_KEY"]
    api_secret = os.environ["CLOUDINARY_API_SECRET"]

    params = {"timestamp": str(int(time.time()))}
    signature = _signature(params, api_secret)

    response = requests.post(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/{resource_type}/upload",
        data={"api_key": api_key, "timestamp": params["timestamp"], "signature": signature},
        files={"file": (filename, file_bytes)},
        timeout=120,
    )
    if not response.ok:
        raise RuntimeError(
            f"Cloudinary-Upload fehlgeschlagen ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}"
        )
    return response.json()["secure_url"]

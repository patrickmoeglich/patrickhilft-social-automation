"""Generates image suggestions via OpenAI (gpt-image-1) and hosts them publicly,
since Ocoya only accepts publicly reachable media URLs, not raw file uploads.

Primaerer Host ist ImgBB. Faellt ImgBB aus (Wartung, 5xx, Timeout), wird automatisch
auf Catbox ausgewichen, damit der Lauf nicht komplett abbricht.
"""
import base64
import os
import time
from typing import Callable, List

import requests

OPENAI_URL = "https://api.openai.com/v1/images/generations"
IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"
CATBOX_UPLOAD_URL = "https://catbox.moe/user/api.php"
IMAGE_MODEL = "gpt-image-1"
IMAGE_SIZE = "1024x1024"
MAX_RETRIES = 3
UPLOAD_RETRIES = 3
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


def _imgbb_upload(image_bytes: bytes) -> str:
    """Laedt Bild-Bytes zu ImgBB hoch und gibt die oeffentliche URL zurueck."""
    response = requests.post(
        IMGBB_UPLOAD_URL,
        params={"key": os.environ["IMGBB_API_KEY"]},
        data={"image": base64.b64encode(image_bytes).decode("ascii")},
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(
            f"ImgBB-Upload fehlgeschlagen ({response.status_code}): "
            f"{response.text[:ERROR_BODY_LIMIT]}"
        )
    data = response.json()
    if not data.get("success"):
        raise RuntimeError(f"ImgBB-Upload fehlgeschlagen: {data}")
    return data["data"]["url"]


def _catbox_upload(image_bytes: bytes) -> str:
    """Fallback-Host: Catbox braucht keinen API-Key und liefert dauerhafte URLs."""
    response = requests.post(
        CATBOX_UPLOAD_URL,
        data={"reqtype": "fileupload"},
        files={"fileToUpload": ("image.png", image_bytes, "image/png")},
        timeout=120,
    )
    url = response.text.strip()
    if not response.ok or not url.startswith("http"):
        raise RuntimeError(
            f"Catbox-Upload fehlgeschlagen ({response.status_code}): "
            f"{response.text[:ERROR_BODY_LIMIT]}"
        )
    return url


def _upload_with_retries(name: str, uploader: Callable[[bytes], str], image_bytes: bytes) -> str:
    last_error: Exception
    for attempt in range(1, UPLOAD_RETRIES + 1):
        try:
            return uploader(image_bytes)
        except Exception as exc:  # noqa: BLE001 - jeder Fehler soll einen Retry ausloesen
            last_error = exc
            print(f"{name}-Upload Versuch {attempt}/{UPLOAD_RETRIES} fehlgeschlagen: {exc}")
            if attempt < UPLOAD_RETRIES:
                time.sleep(2 ** attempt)
    raise last_error


UPLOAD_HOSTS = (("ImgBB", _imgbb_upload), ("Catbox", _catbox_upload))


def upload_image(image_bytes: bytes) -> str:
    """Laedt Bild-Bytes hoch und gibt eine oeffentlich erreichbare URL zurueck.

    Reihenfolge: ImgBB (3 Versuche mit Backoff), danach Catbox (3 Versuche mit Backoff).
    Erst wenn beide Hosts scheitern, wird ein Fehler geworfen.
    """
    errors = []
    for index, (name, uploader) in enumerate(UPLOAD_HOSTS):
        try:
            url = _upload_with_retries(name, uploader, image_bytes)
            if index > 0:
                print(f"Hinweis: Bild ueber Fallback-Host {name} gehostet.")
            return url
        except Exception as exc:  # noqa: BLE001 - naechsten Host probieren
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Bild-Upload bei allen Hosts fehlgeschlagen -> " + " | ".join(errors))


# Rueckwaertskompatibler Alias: main.py und daily/ importieren weiterhin upload_to_imgbb.
upload_to_imgbb = upload_image


def generate_image_suggestions(prompts: List[str]) -> List[str]:
    """Generates one image per prompt via OpenAI and returns public image URLs."""
    return [upload_image(_generate_image_bytes(prompt)) for prompt in prompts]

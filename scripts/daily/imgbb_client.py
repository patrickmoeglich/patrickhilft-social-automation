"""Minimaler ImgBB-Upload-Client fuer die Bildkarten des taeglichen Kanals.
ImgBB hostet nur Bilder - fuer den reinen Kartenkanal reicht das, Cloudinary
wird nicht mehr benoetigt."""
import base64
import os

import requests

UPLOAD_URL = "https://api.imgbb.com/1/upload"
ERROR_BODY_LIMIT = 500


def upload(image_bytes: bytes) -> str:
    """Laedt Bild-Bytes zu ImgBB hoch und liefert die oeffentliche URL."""
    response = requests.post(
        UPLOAD_URL,
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

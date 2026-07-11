"""LinkedIn API client (versioned REST API): image + video posts.

Setup (self-serve, no App Review needed):
1. Create a LinkedIn App (linkedin.com/developers), add the "Share on LinkedIn"
   and "Sign In with LinkedIn using OpenID Connect" products.
2. Run the 3-legged OAuth flow once (manually, e.g. via Postman or a short
   local script) with scopes `openid profile w_member_social` to get an
   access token. LinkedIn access tokens expire after ~60 days and must be
   refreshed manually unless your app has refresh-token access - budget for
   re-authenticating periodically.
3. LINKEDIN_ACCESS_TOKEN=<token>, LINKEDIN_PERSON_URN=urn:li:person:<id>
   (fetch the id once via GET https://api.linkedin.com/v2/userinfo).
"""
import os

import requests

API_BASE = "https://api.linkedin.com/rest"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_VERSION = "202401"
ERROR_BODY_LIMIT = 500


def _headers(extra: dict = None) -> dict:
    headers = {
        "Authorization": f"Bearer {os.environ['LINKEDIN_ACCESS_TOKEN']}",
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }
    if extra:
        headers.update(extra)
    return headers


def _check(response: requests.Response) -> dict:
    if not response.ok:
        raise RuntimeError(f"LinkedIn-API-Fehler ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}")
    return response.json() if response.content else {}


def whoami() -> dict:
    """Validates the access token without posting anything."""
    response = requests.get(USERINFO_URL, headers=_headers(), timeout=30)
    return _check(response)


def _person_urn() -> str:
    return os.environ["LINKEDIN_PERSON_URN"]


def _create_post(commentary: str, media_urn: str = None, media_kind: str = None) -> dict:
    body = {
        "author": _person_urn(),
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if media_urn:
        body["content"] = {"media": {"id": media_urn}}
        if media_kind == "video":
            body["content"]["media"]["title"] = "Video"

    response = requests.post(
        f"{API_BASE}/posts",
        headers=_headers({"Content-Type": "application/json"}),
        json=body,
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"LinkedIn-API-Fehler ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}")
    return {"id": response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")}


def publish_image(image_bytes: bytes, caption: str) -> dict:
    init = _check(
        requests.post(
            f"{API_BASE}/images?action=initializeUpload",
            headers=_headers({"Content-Type": "application/json"}),
            json={"initializeUploadRequest": {"owner": _person_urn()}},
            timeout=60,
        )
    )
    upload_url = init["value"]["uploadUrl"]
    image_urn = init["value"]["image"]

    upload_response = requests.put(upload_url, data=image_bytes, timeout=120)
    if not upload_response.ok:
        raise RuntimeError(f"LinkedIn-Bild-Upload fehlgeschlagen ({upload_response.status_code})")

    return _create_post(caption, media_urn=image_urn)


def publish_video(video_bytes: bytes, caption: str) -> dict:
    init = _check(
        requests.post(
            f"{API_BASE}/videos?action=initializeUpload",
            headers=_headers({"Content-Type": "application/json"}),
            json={
                "initializeUploadRequest": {
                    "owner": _person_urn(),
                    "fileSizeBytes": len(video_bytes),
                    "uploadCaptions": False,
                    "uploadThumbnail": False,
                }
            },
            timeout=60,
        )
    )
    video_urn = init["value"]["video"]
    upload_instructions = init["value"]["uploadInstructions"]

    uploaded_part_ids = []
    for instruction in upload_instructions:
        chunk = video_bytes[instruction["firstByte"]: instruction["lastByte"] + 1]
        upload_response = requests.put(instruction["uploadUrl"], data=chunk, timeout=120)
        if not upload_response.ok:
            raise RuntimeError(f"LinkedIn-Video-Upload fehlgeschlagen ({upload_response.status_code})")
        etag = upload_response.headers.get("ETag")
        if etag:
            uploaded_part_ids.append(etag)

    _check(
        requests.post(
            f"{API_BASE}/videos?action=finalizeUpload",
            headers=_headers({"Content-Type": "application/json"}),
            json={"finalizeUploadRequest": {"video": video_urn, "uploadedPartIds": uploaded_part_ids}},
            timeout=60,
        )
    )

    return _create_post(caption, media_urn=video_urn, media_kind="video")

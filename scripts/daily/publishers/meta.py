"""Meta Graph API client: Instagram (feed image + Reels) and Facebook Page
(image + video posts).

Setup (no App Review needed as long as the poster is an admin/tester on the
Meta App in Development Mode - see README):
1. Create a Meta App (developers.facebook.com) of type "Business".
2. Add the Instagram Graph API + Facebook Login for Business products.
3. Connect the Instagram professional account to a Facebook Page you manage.
4. Generate a long-lived Page Access Token with `instagram_basic`,
   `instagram_content_publish`, `pages_read_engagement`, `pages_manage_posts`.
5. META_PAGE_ACCESS_TOKEN=<token>, META_PAGE_ID=<page id>,
   META_IG_USER_ID=<connected Instagram Business Account id>.
"""
import os
import time

import requests

BASE_URL = "https://graph.facebook.com/v20.0"
ERROR_BODY_LIMIT = 500
POLL_INTERVAL_SECONDS = 5
POLL_MAX_ATTEMPTS = 24  # ~2 minutes


def _access_token() -> str:
    return os.environ["META_PAGE_ACCESS_TOKEN"]


def _check(response: requests.Response) -> dict:
    if not response.ok:
        raise RuntimeError(f"Meta-API-Fehler ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}")
    return response.json()


def whoami() -> dict:
    """Validates the access token without posting anything."""
    response = requests.get(f"{BASE_URL}/me", params={"access_token": _access_token()}, timeout=30)
    return _check(response)


def _poll_container_until_finished(container_id: str) -> None:
    for _ in range(POLL_MAX_ATTEMPTS):
        response = requests.get(
            f"{BASE_URL}/{container_id}",
            params={"fields": "status_code", "access_token": _access_token()},
            timeout=30,
        )
        data = _check(response)
        status = data.get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Instagram-Media-Container fehlgeschlagen: {data}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Instagram-Media-Container {container_id} wurde nicht rechtzeitig fertig.")


def publish_instagram_image(image_url: str, caption: str) -> dict:
    ig_user_id = os.environ["META_IG_USER_ID"]
    container = _check(
        requests.post(
            f"{BASE_URL}/{ig_user_id}/media",
            data={"image_url": image_url, "caption": caption, "access_token": _access_token()},
            timeout=60,
        )
    )
    _poll_container_until_finished(container["id"])
    return _check(
        requests.post(
            f"{BASE_URL}/{ig_user_id}/media_publish",
            data={"creation_id": container["id"], "access_token": _access_token()},
            timeout=60,
        )
    )


def publish_instagram_reel(video_url: str, caption: str) -> dict:
    ig_user_id = os.environ["META_IG_USER_ID"]
    container = _check(
        requests.post(
            f"{BASE_URL}/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": _access_token(),
            },
            timeout=60,
        )
    )
    _poll_container_until_finished(container["id"])
    return _check(
        requests.post(
            f"{BASE_URL}/{ig_user_id}/media_publish",
            data={"creation_id": container["id"], "access_token": _access_token()},
            timeout=60,
        )
    )


def publish_facebook_image(image_url: str, caption: str) -> dict:
    page_id = os.environ["META_PAGE_ID"]
    return _check(
        requests.post(
            f"{BASE_URL}/{page_id}/photos",
            data={"url": image_url, "caption": caption, "access_token": _access_token()},
            timeout=60,
        )
    )


def publish_facebook_video(video_url: str, caption: str) -> dict:
    """Posts a normal Page video (appears in the Feed). Note: this does not use
    Facebook's dedicated Reels-placement upload flow (resumable upload session
    with explicit video_state), which is more involved - a plain Page video post
    is the pragmatic default here."""
    page_id = os.environ["META_PAGE_ID"]
    return _check(
        requests.post(
            f"{BASE_URL}/{page_id}/videos",
            data={"file_url": video_url, "description": caption, "access_token": _access_token()},
            timeout=120,
        )
    )

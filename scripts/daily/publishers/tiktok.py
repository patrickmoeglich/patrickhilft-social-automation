"""TikTok Content Posting API client (Direct Post, PULL_FROM_URL).

Setup:
1. Create a TikTok Developer App (developers.tiktok.com), add the
   "Content Posting API" product with scope `video.publish`.
2. Run the OAuth flow once to get an access token for your own account.
3. IMPORTANT: until TikTok audits your app for the `video.publish` scope,
   Direct Post only works with `privacy_level=SELF_ONLY` (private draft visible
   only to you) - public posting requires a completed app audit, which can take
   several days. Set TIKTOK_PRIVACY_LEVEL=PUBLIC_TO_EVERYONE only after the
   audit is approved.
4. TIKTOK_ACCESS_TOKEN=<token>.
"""
import os
import time

import requests

INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
USERINFO_URL = "https://open.tiktokapis.com/v2/user/info/"
ERROR_BODY_LIMIT = 500
POLL_INTERVAL_SECONDS = 5
POLL_MAX_ATTEMPTS = 24


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['TIKTOK_ACCESS_TOKEN']}",
        "Content-Type": "application/json",
    }


def _check(response: requests.Response) -> dict:
    if not response.ok:
        raise RuntimeError(f"TikTok-API-Fehler ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}")
    data = response.json()
    if data.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok-API-Fehler: {data['error']}")
    return data


def whoami() -> dict:
    """Validates the access token without posting anything."""
    response = requests.get(
        USERINFO_URL, params={"fields": "open_id,display_name"}, headers=_headers(), timeout=30
    )
    return _check(response)


def publish_video(video_url: str, caption: str) -> dict:
    privacy_level = os.environ.get("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")
    body = {
        "post_info": {
            "title": caption,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
    }
    init = _check(requests.post(INIT_URL, json=body, headers=_headers(), timeout=60))
    publish_id = init["data"]["publish_id"]

    for _ in range(POLL_MAX_ATTEMPTS):
        status = _check(
            requests.post(STATUS_URL, json={"publish_id": publish_id}, headers=_headers(), timeout=30)
        )
        status_code = status["data"]["status"]
        if status_code == "PUBLISH_COMPLETE":
            return status["data"]
        if status_code == "FAILED":
            raise RuntimeError(f"TikTok-Veroeffentlichung fehlgeschlagen: {status['data']}")
        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(f"TikTok-Post {publish_id} wurde nicht rechtzeitig veroeffentlicht.")

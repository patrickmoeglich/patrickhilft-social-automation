"""X (Twitter) API client: chunked media upload (v1.1) + tweet creation (v2).

Setup:
1. Create a Developer App at developer.x.com with "Read and Write" permissions,
   OAuth 1.0a User Context (needed for media upload, v2-only auth cannot upload media).
2. Generate Consumer Keys (API Key/Secret) and Access Token/Secret for your own account.
3. Free tier covers 500 writes/month, which is enough for 1 post/day.
4. X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET.
"""
import os
import time

from requests_oauthlib import OAuth1Session

UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEETS_URL = "https://api.twitter.com/2/tweets"
USERS_ME_URL = "https://api.twitter.com/2/users/me"
CHUNK_SIZE = 4 * 1024 * 1024
ERROR_BODY_LIMIT = 500
POLL_INTERVAL_SECONDS = 3
POLL_MAX_ATTEMPTS = 40


def _session() -> OAuth1Session:
    return OAuth1Session(
        client_key=os.environ["X_API_KEY"],
        client_secret=os.environ["X_API_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_SECRET"],
    )


def _check(response) -> dict:
    if not response.ok:
        raise RuntimeError(f"X-API-Fehler ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}")
    return response.json() if response.content else {}


def whoami() -> dict:
    """Validates the credentials without posting anything."""
    return _check(_session().get(USERS_ME_URL, timeout=30))


def _upload_media(media_bytes: bytes, media_type: str, media_category: str) -> str:
    session = _session()

    init = _check(
        session.post(
            UPLOAD_URL,
            data={
                "command": "INIT",
                "total_bytes": len(media_bytes),
                "media_type": media_type,
                "media_category": media_category,
            },
            timeout=60,
        )
    )
    media_id = init["media_id_string"]

    for segment_index, offset in enumerate(range(0, len(media_bytes), CHUNK_SIZE)):
        chunk = media_bytes[offset: offset + CHUNK_SIZE]
        response = session.post(
            UPLOAD_URL,
            data={"command": "APPEND", "media_id": media_id, "segment_index": segment_index},
            files={"media": chunk},
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(f"X-Media-Upload (APPEND) fehlgeschlagen ({response.status_code}): {response.text[:ERROR_BODY_LIMIT]}")

    _check(session.post(UPLOAD_URL, data={"command": "FINALIZE", "media_id": media_id}, timeout=60))

    for _ in range(POLL_MAX_ATTEMPTS):
        status = _check(
            session.get(UPLOAD_URL, params={"command": "STATUS", "media_id": media_id}, timeout=30)
        )
        processing_info = status.get("processing_info")
        if not processing_info or processing_info.get("state") == "succeeded":
            return media_id
        if processing_info.get("state") == "failed":
            raise RuntimeError(f"X-Media-Verarbeitung fehlgeschlagen: {processing_info}")
        time.sleep(max(processing_info.get("check_after_secs", POLL_INTERVAL_SECONDS), 1))

    raise RuntimeError(f"X-Media {media_id} wurde nicht rechtzeitig verarbeitet.")


def _post_tweet(text: str, media_id: str) -> dict:
    return _check(
        _session().post(TWEETS_URL, json={"text": text, "media": {"media_ids": [media_id]}}, timeout=60)
    )


def publish_image(image_bytes: bytes, caption: str) -> dict:
    media_id = _upload_media(image_bytes, media_type="image/png", media_category="tweet_image")
    return _post_tweet(caption, media_id)


def publish_video(video_bytes: bytes, caption: str) -> dict:
    media_id = _upload_media(video_bytes, media_type="video/mp4", media_category="tweet_video")
    return _post_tweet(caption, media_id)

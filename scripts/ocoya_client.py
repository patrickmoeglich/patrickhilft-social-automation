"""Minimal Ocoya API client (create post as draft, then schedule it for later)."""
import os
import time
from typing import List, Optional

import requests

BASE_URL = "https://app.ocoya.com/api/_public/v1"
ERROR_BODY_LIMIT = 500
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


class OcoyaClient:
    def __init__(self, api_key: Optional[str] = None, workspace_id: Optional[str] = None):
        self.api_key = api_key or os.environ["OCOYA_API_KEY"]
        self.workspace_id = workspace_id or os.environ["OCOYA_WORKSPACE_ID"]
        if not self.api_key:
            raise RuntimeError("OCOYA_API_KEY ist leer - GitHub Secret pruefen/neu setzen.")
        if not self.workspace_id:
            raise RuntimeError("OCOYA_WORKSPACE_ID ist leer - GitHub Secret pruefen/neu setzen.")

    def _headers(self) -> dict:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _check(response: requests.Response) -> dict:
        if not response.ok:
            raise RuntimeError(
                f"Ocoya-API-Fehler ({response.status_code}) fuer {response.url}: "
                f"{response.text[:ERROR_BODY_LIMIT]}"
            )
        return response.json()

    def _request(self, method: str, path: str, params: dict = None, **kwargs) -> dict:
        """Fuehrt einen Ocoya-Request aus und wiederholt ihn bei 5xx oder Netzfehlern.

        Ocoya liefert bei internen Fehlern eine HTML-Seite mit Status 500 statt einer
        JSON-Antwort. Das ist meist voruebergehend - kurz warten und erneut versuchen,
        statt den ganzen Lauf abzubrechen.
        """
        url = f"{BASE_URL}{path}"
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.request(
                    method, url, headers=self._headers(), params=params, timeout=30, **kwargs
                )
                if response.status_code >= 500 and attempt < MAX_RETRIES:
                    last_error = (
                        f"Ocoya-API-Fehler ({response.status_code}) fuer {response.url}: "
                        f"{response.text[:ERROR_BODY_LIMIT]}"
                    )
                    print(f"Ocoya Versuch {attempt}/{MAX_RETRIES} fehlgeschlagen: {last_error}")
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                return self._check(response)
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise
                print(f"Ocoya Versuch {attempt}/{MAX_RETRIES} fehlgeschlagen: {exc}")
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise RuntimeError(last_error or "Ocoya-Request fehlgeschlagen")

    def list_workspaces(self) -> list:
        return self._request("GET", "/workspaces")

    def list_social_profiles(self) -> list:
        return self._request("GET", "/social-profiles", params={"workspaceId": self.workspace_id})

    def create_draft_post(self, caption: str, social_profile_ids: List[str], media_urls: Optional[List[str]] = None) -> dict:
        body = {"caption": caption, "socialProfileIds": social_profile_ids}
        if media_urls:
            body["mediaUrls"] = media_urls
        return self._request("POST", "/post", params={"workspaceId": self.workspace_id}, json=body)

    def schedule_post(self, post_id: str, scheduled_at_iso: str) -> dict:
        return self._request(
            "PATCH",
            f"/post/{post_id}",
            params={"workspaceId": self.workspace_id},
            json={"scheduledAt": scheduled_at_iso},
        )

    def create_and_schedule(
        self,
        caption: str,
        social_profile_ids: List[str],
        scheduled_at_iso: str,
        media_urls: Optional[List[str]] = None,
    ) -> dict:
        draft = self.create_draft_post(caption, social_profile_ids, media_urls)
        post_id = draft.get("postGroupId") or draft.get("id") or draft.get("_id")
        if not post_id:
            raise RuntimeError(f"Ocoya-Antwort enthielt keine Post-ID: {draft}")
        return self.schedule_post(post_id, scheduled_at_iso)

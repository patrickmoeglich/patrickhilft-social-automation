"""Minimal Ocoya API client (create post as draft, then schedule it for later)."""
import os
from typing import List, Optional

import requests

BASE_URL = "https://app.ocoya.com/api/_public/v1"


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

    def list_workspaces(self) -> list:
        response = requests.get(f"{BASE_URL}/workspaces", headers=self._headers(), timeout=30)
        response.raise_for_status()
        return response.json()

    def list_social_profiles(self) -> list:
        response = requests.get(
            f"{BASE_URL}/social-profiles",
            headers=self._headers(),
            params={"workspaceId": self.workspace_id},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def create_draft_post(self, caption: str, social_profile_ids: List[str], media_urls: Optional[List[str]] = None) -> dict:
        body = {"caption": caption, "socialProfileIds": social_profile_ids}
        if media_urls:
            body["mediaUrls"] = media_urls
        response = requests.post(
            f"{BASE_URL}/post",
            headers=self._headers(),
            params={"workspaceId": self.workspace_id},
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def schedule_post(self, post_id: str, scheduled_at_iso: str) -> dict:
        response = requests.patch(
            f"{BASE_URL}/post/{post_id}",
            headers=self._headers(),
            params={"workspaceId": self.workspace_id},
            json={"scheduledAt": scheduled_at_iso},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def create_and_schedule(
        self,
        caption: str,
        social_profile_ids: List[str],
        scheduled_at_iso: str,
        media_urls: Optional[List[str]] = None,
    ) -> dict:
        draft = self.create_draft_post(caption, social_profile_ids, media_urls)
        post_id = draft.get("id") or draft.get("_id")
        if not post_id:
            raise RuntimeError(f"Ocoya-Antwort enthielt keine Post-ID: {draft}")
        return self.schedule_post(post_id, scheduled_at_iso)

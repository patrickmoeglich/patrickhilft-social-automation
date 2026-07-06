"""Einmaliges lokales Hilfsskript: zeigt Workspace-IDs und Social-Profile-IDs an.

Diese IDs brauchst du, um OCOYA_WORKSPACE_ID und OCOYA_SOCIAL_PROFILE_IDS
als GitHub Secrets zu hinterlegen (siehe README).

Aufruf lokal:
    OCOYA_API_KEY=dein_key python scripts/list_ocoya_resources.py
"""
import os
import sys

import requests

BASE_URL = "https://app.ocoya.com/api/_public/v1"


def main() -> None:
    api_key = os.environ.get("OCOYA_API_KEY")
    if not api_key:
        print("Bitte OCOYA_API_KEY als Umgebungsvariable setzen.", file=sys.stderr)
        sys.exit(1)

    headers = {"X-API-Key": api_key, "Accept": "application/json"}

    workspaces = requests.get(f"{BASE_URL}/workspaces", headers=headers, timeout=30)
    workspaces.raise_for_status()
    print("=== Workspaces ===")
    print(workspaces.json())

    workspace_id = os.environ.get("OCOYA_WORKSPACE_ID")
    if not workspace_id:
        print(
            "\nSetze zusätzlich OCOYA_WORKSPACE_ID (aus der Liste oben), "
            "um auch die Social-Profile aufzulisten.",
        )
        return

    profiles = requests.get(
        f"{BASE_URL}/social-profiles",
        headers=headers,
        params={"workspaceId": workspace_id},
        timeout=30,
    )
    profiles.raise_for_status()
    print("\n=== Social Profiles ===")
    print(profiles.json())


if __name__ == "__main__":
    main()

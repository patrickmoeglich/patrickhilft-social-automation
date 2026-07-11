"""Best-effort Telegram notification (info only - no approval gate, no buttons).

Silently does nothing if TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID aren't set, so this
program stays fully self-contained and doesn't require Telegram to run.
"""
import os

import requests


def send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=30,
        )
    except requests.RequestException as exc:
        print(f"Telegram-Benachrichtigung fehlgeschlagen (ignoriert): {exc}")

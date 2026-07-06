"""Minimal Telegram Bot API client (long polling, no webhook needed)."""
import os
import time
from typing import Optional

import requests

API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]

    def _call(self, method: str, **params) -> dict:
        url = API_BASE.format(token=self.token, method=method)
        response = requests.post(url, json=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {data}")
        return data["result"]

    def send_message(self, text: str, reply_markup: Optional[dict] = None) -> int:
        result = self._call(
            "sendMessage",
            chat_id=self.chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return result["message_id"]

    def edit_message(self, message_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
        self._call(
            "editMessageText",
            chat_id=self.chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

    def get_updates(self, offset: int, timeout: int = 25) -> list:
        result = self._call("getUpdates", offset=offset, timeout=timeout, allowed_updates=["callback_query"])
        return result

    def wait_for_decision(self, message_id: int, timeout_seconds: int) -> Optional[str]:
        """Long-polls until a callback_query for `message_id` arrives or the timeout elapses.

        Returns the callback_data string ("approve" / "regenerate" / "cancel") or None on timeout.
        """
        deadline = time.monotonic() + timeout_seconds
        offset = 0
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            poll_timeout = int(min(25, max(1, remaining)))
            updates = self.get_updates(offset=offset, timeout=poll_timeout)
            for update in updates:
                offset = update["update_id"] + 1
                callback = update.get("callback_query")
                if not callback:
                    continue
                if callback.get("message", {}).get("message_id") != message_id:
                    # Stale callback from an older message (e.g. a previous run) - ack and ignore.
                    self.answer_callback_query(callback["id"])
                    continue
                self.answer_callback_query(callback["id"])
                return callback["data"]
        return None


def approval_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Freigeben", "callback_data": "approve"},
                {"text": "\U0001F504 Neu generieren", "callback_data": "regenerate"},
                {"text": "❌ Abbrechen", "callback_data": "cancel"},
            ]
        ]
    }

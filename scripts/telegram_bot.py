"""Minimal Telegram Bot API client (long polling, no webhook needed)."""
import os
import time
from typing import List, Optional, Tuple

import requests

API_BASE = "https://api.telegram.org/bot{token}/{method}"
FILE_BASE = "https://api.telegram.org/file/bot{token}/{file_path}"


class TelegramBot:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]

    def _call(self, method: str, **params) -> dict:
        url = API_BASE.format(token=self.token, method=method)
        response = requests.post(url, json=params, timeout=30)
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise
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

    def send_media_group(self, photo_urls: List[str], caption: str = "") -> List[int]:
        media = []
        for i, url in enumerate(photo_urls):
            item = {"type": "photo", "media": url}
            if i == 0 and caption:
                item["caption"] = caption
            media.append(item)
        result = self._call("sendMediaGroup", chat_id=self.chat_id, media=media)
        return [message["message_id"] for message in result]

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        self._call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

    def get_updates(self, offset: int, timeout: int = 25) -> list:
        return self._call(
            "getUpdates",
            offset=offset,
            timeout=timeout,
            allowed_updates=["callback_query", "message"],
        )

    def get_file_path(self, file_id: str) -> str:
        result = self._call("getFile", file_id=file_id)
        return result["file_path"]

    def download_file(self, file_path: str) -> bytes:
        url = FILE_BASE.format(token=self.token, file_path=file_path)
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.content

    def wait_for_decision(self, message_id: int, timeout_seconds: int) -> Optional[str]:
        """Long-polls until a callback_query for `message_id` arrives or the timeout elapses.

        Returns the callback_data string or None on timeout.
        """
        result = self._wait(message_id, timeout_seconds, want_photo=False)
        return result[1] if result else None

    def wait_for_callback_or_photo(self, message_id: int, timeout_seconds: int) -> Optional[Tuple[str, str]]:
        """Long-polls for either a callback_query on `message_id`, or any photo message
        sent to the chat (e.g. the user uploading their own image).

        Returns ("callback", data), ("photo", file_id), or None on timeout.
        """
        return self._wait(message_id, timeout_seconds, want_photo=True)

    def _wait(self, message_id: int, timeout_seconds: int, want_photo: bool) -> Optional[Tuple[str, str]]:
        deadline = time.monotonic() + timeout_seconds
        offset = 0
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            poll_timeout = int(min(25, max(1, remaining)))
            updates = self.get_updates(offset=offset, timeout=poll_timeout)
            for update in updates:
                offset = update["update_id"] + 1
                callback = update.get("callback_query")
                if callback:
                    if callback.get("message", {}).get("message_id") != message_id:
                        # Stale callback from an older message (e.g. a previous run) - ack and ignore.
                        self.answer_callback_query(callback["id"])
                        continue
                    self.answer_callback_query(callback["id"])
                    return ("callback", callback["data"])
                message = update.get("message")
                if (
                    want_photo
                    and message
                    and message.get("photo")
                    and str(message.get("chat", {}).get("id")) == str(self.chat_id)
                ):
                    return ("photo", message["photo"][-1]["file_id"])
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


def image_choice_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "1️⃣ Bild 1", "callback_data": "img_0"},
                {"text": "2️⃣ Bild 2", "callback_data": "img_1"},
                {"text": "3️⃣ Bild 3", "callback_data": "img_2"},
            ],
            [
                {"text": "\U0001F4E4 Eigenes Bild hochladen", "callback_data": "own_image"},
                {"text": "\U0001F504 Neue Vorschläge", "callback_data": "regenerate_images"},
            ],
            [
                {"text": "❌ Abbrechen", "callback_data": "cancel"},
            ],
        ]
    }

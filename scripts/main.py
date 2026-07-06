"""Orchestriert den woechentlichen Social-Media-Post:

1. Claude generiert einen Text-Entwurf (Thema + Caption + Hashtags)
2. Der Text wird per Telegram zur Freigabe geschickt (Freigeben / Neu generieren / Abbrechen)
3. Nach Freigabe generiert Claude 3 Bildideen, OpenAI erzeugt dazu Bilder (gehostet auf ImgBB)
4. Die 3 Bilder werden per Telegram geschickt - Auswahl eines Bildes, eigenes Bild hochladen,
   neue Vorschlaege anfordern, oder abbrechen
5. Der Post wird mit Text + gewaehltem Bild ueber Ocoya fuer einen festen Zeitpunkt eingeplant
6. Der Ausgang wird per Telegram bestaetigt
"""
import html
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from generate_post import generate_image_prompts, generate_post
from image_gen import generate_image_suggestions, upload_to_imgbb
from ocoya_client import OcoyaClient
from telegram_bot import TelegramBot, approval_keyboard, image_choice_keyboard

MAX_REGENERATIONS = int(os.environ.get("MAX_REGENERATIONS", "4"))
MAX_IMAGE_REGENERATIONS = int(os.environ.get("MAX_IMAGE_REGENERATIONS", "2"))
POLL_TIMEOUT_MINUTES = int(os.environ.get("POLL_TIMEOUT_MINUTES", "60"))
POST_SCHEDULE_HOUR = int(os.environ.get("POST_SCHEDULE_HOUR", "10"))
POST_SCHEDULE_TIMEZONE = os.environ.get("POST_SCHEDULE_TIMEZONE", "Europe/Berlin")
REGENERATE_FEEDBACK = (
    "Bitte eine spuerbar andere Variante erstellen: anderer Blickwinkel, "
    "andere Formulierung, ggf. anderes Unterthema."
)
REGENERATE_IMAGE_FEEDBACK = "Bitte spuerbar andere Motive, Perspektiven oder Stile vorschlagen."
# Telegram-Nachrichten sind auf 4096 Zeichen begrenzt; lange Fehlertexte (z.B. HTML-Fehlerseiten
# von APIs) werden gekuerzt, damit die Fehlermeldung selbst zuverlaessig zugestellt wird.
TELEGRAM_ERROR_TEXT_LIMIT = 3000


def _error_text(exc: Exception) -> str:
    text = str(exc)
    if len(text) > TELEGRAM_ERROR_TEXT_LIMIT:
        text = text[:TELEGRAM_ERROR_TEXT_LIMIT] + "\n... (gekürzt)"
    return html.escape(text)


def _format_message(draft: dict) -> str:
    caption = html.escape(draft["caption"])
    hashtags = " ".join(f"#{tag.lstrip('#')}" for tag in draft["hashtags"])
    topic = html.escape(draft["topic"])
    return (
        f"<b>Neuer Post-Entwurf</b>\n"
        f"<i>Thema: {topic}</i>\n\n"
        f"{caption}\n\n"
        f"{html.escape(hashtags)}"
    )


def _format_image_choice_message() -> str:
    return (
        "<b>Bildvorschläge</b>\n"
        "Wähle eins der drei Bilder oben, lade ein eigenes Bild hoch, oder fordere neue "
        "Vorschläge an."
    )


def _caption_with_tags(draft: dict) -> str:
    return draft["caption"] + "\n\n" + " ".join(f"#{tag.lstrip('#')}" for tag in draft["hashtags"])


def _social_profile_ids() -> list:
    raw = os.environ["OCOYA_SOCIAL_PROFILE_IDS"]
    ids = [pid.strip().strip("[]\"'") for pid in raw.split(",")]
    ids = [pid for pid in ids if pid]
    print(f"OCOYA_SOCIAL_PROFILE_IDS geparst ({len(ids)}): {ids}")
    return ids


def _next_schedule_time() -> datetime:
    tz = ZoneInfo(POST_SCHEDULE_TIMEZONE)
    now = datetime.now(tz)
    return (now + timedelta(days=1)).replace(hour=POST_SCHEDULE_HOUR, minute=0, second=0, microsecond=0)


def _approve_text(bot: TelegramBot) -> Optional[dict]:
    """Generiert den Text-Entwurf und laesst ihn per Telegram freigeben.

    Returns den freigegebenen Entwurf, oder None wenn abgebrochen/Zeitlimit erreicht.
    """
    try:
        draft = generate_post()
    except Exception as exc:
        bot.send_message(f"🚨 <b>Fehler bei der Post-Generierung:</b>\n{_error_text(exc)}")
        raise

    message_id = bot.send_message(_format_message(draft), reply_markup=approval_keyboard())

    regenerations = 0
    while True:
        decision = bot.wait_for_decision(message_id, timeout_seconds=POLL_TIMEOUT_MINUTES * 60)

        if decision is None:
            bot.edit_message(
                message_id,
                _format_message(draft) + "\n\n⏱ <b>Zeitlimit erreicht - kein Post veroeffentlicht.</b>",
            )
            return None

        if decision == "cancel":
            bot.edit_message(
                message_id,
                _format_message(draft) + "\n\n❌ <b>Abgebrochen - kein Post veroeffentlicht.</b>",
            )
            return None

        if decision == "regenerate":
            regenerations += 1
            if regenerations > MAX_REGENERATIONS:
                bot.edit_message(
                    message_id,
                    _format_message(draft) + "\n\n⚠️ <b>Limit fuer Neu-Generierungen erreicht.</b>",
                )
                return None
            bot.edit_message(message_id, _format_message(draft) + "\n\n⏳ Neuer Entwurf wird erstellt ...")
            draft = generate_post(feedback=REGENERATE_FEEDBACK)
            bot.edit_message(message_id, _format_message(draft), reply_markup=approval_keyboard())
            continue

        if decision == "approve":
            bot.edit_message(message_id, _format_message(draft) + "\n\n✅ <b>Text freigegeben.</b>")
            return draft


def _select_image(bot: TelegramBot, draft: dict) -> Optional[str]:
    """Schickt 3 Bildvorschlaege per Telegram und laesst eins auswaehlen.

    Returns die oeffentliche Bild-URL, oder None wenn abgebrochen/Zeitlimit erreicht.
    """
    image_prompts = generate_image_prompts(draft["topic"], draft["caption"])
    image_urls = generate_image_suggestions(image_prompts)
    bot.send_media_group(image_urls, caption="Bildvorschläge für den Post")
    choice_message_id = bot.send_message(_format_image_choice_message(), reply_markup=image_choice_keyboard())

    image_regenerations = 0
    while True:
        result = bot.wait_for_callback_or_photo(choice_message_id, timeout_seconds=POLL_TIMEOUT_MINUTES * 60)

        if result is None:
            bot.edit_message(
                choice_message_id,
                _format_image_choice_message() + "\n\n⏱ <b>Zeitlimit erreicht - kein Post veroeffentlicht.</b>",
            )
            return None

        kind, value = result

        if kind == "callback" and value == "cancel":
            bot.edit_message(
                choice_message_id,
                _format_image_choice_message() + "\n\n❌ <b>Abgebrochen - kein Post veroeffentlicht.</b>",
            )
            return None

        if kind == "callback" and value == "regenerate_images":
            image_regenerations += 1
            if image_regenerations > MAX_IMAGE_REGENERATIONS:
                bot.edit_message(
                    choice_message_id,
                    _format_image_choice_message() + "\n\n⚠️ <b>Limit fuer neue Bildvorschlaege erreicht.</b>",
                )
                return None
            bot.edit_message(choice_message_id, "⏳ Neue Bildvorschläge werden erstellt ...")
            image_prompts = generate_image_prompts(draft["topic"], draft["caption"], feedback=REGENERATE_IMAGE_FEEDBACK)
            image_urls = generate_image_suggestions(image_prompts)
            bot.send_media_group(image_urls, caption="Neue Bildvorschläge für den Post")
            bot.edit_message(choice_message_id, _format_image_choice_message(), reply_markup=image_choice_keyboard())
            continue

        if kind == "callback" and value.startswith("img_"):
            index = int(value.split("_")[1])
            bot.edit_message(choice_message_id, _format_image_choice_message() + "\n\n✅ <b>Bild ausgewählt.</b>")
            return image_urls[index]

        if kind == "callback" and value == "own_image":
            bot.edit_message(choice_message_id, "📤 Bitte jetzt ein Bild an diesen Chat senden.")
            upload_result = bot.wait_for_callback_or_photo(choice_message_id, timeout_seconds=POLL_TIMEOUT_MINUTES * 60)

            if upload_result is None:
                bot.send_message("⏱ <b>Zeitlimit erreicht - kein Bild erhalten, Abbruch.</b>")
                return None

            upload_kind, upload_value = upload_result
            if upload_kind == "callback" and upload_value == "cancel":
                bot.send_message("❌ <b>Abgebrochen - kein Post veroeffentlicht.</b>")
                return None
            if upload_kind != "photo":
                bot.send_message("⚠️ <b>Kein Bild erhalten - Abbruch.</b>")
                return None

            file_path = bot.get_file_path(upload_value)
            image_bytes = bot.download_file(file_path)
            return upload_to_imgbb(image_bytes)

        # Unbekannte/veraltete Callback-Daten - ignorieren und weiter warten.


def main() -> int:
    bot = TelegramBot()

    draft = _approve_text(bot)
    if draft is None:
        return 0

    try:
        media_url = _select_image(bot, draft)
    except Exception as exc:
        bot.send_message(f"🚨 <b>Fehler bei der Bildauswahl:</b>\n{_error_text(exc)}")
        raise
    if media_url is None:
        return 0

    scheduled_at = _next_schedule_time()
    try:
        OcoyaClient().create_and_schedule(
            _caption_with_tags(draft),
            _social_profile_ids(),
            scheduled_at.isoformat(),
            media_urls=[media_url],
        )
    except Exception as exc:
        bot.send_message(f"🚨 <b>Fehler beim Einplanen:</b>\n{_error_text(exc)}")
        raise

    bot.send_message(f"✅ <b>Post eingeplant für {scheduled_at.strftime('%d.%m.%Y %H:%M %Z')}!</b>")
    print(f"Post erfolgreich eingeplant fuer {scheduled_at.isoformat()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

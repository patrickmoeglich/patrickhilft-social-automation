"""Orchestriert den woechentlichen Social-Media-Post:

1. Claude generiert einen Entwurf (Thema + Caption + Hashtags)
2. Der Entwurf wird per Telegram zur Freigabe geschickt (Freigeben / Neu generieren / Abbrechen)
3. Bei Freigabe wird der Post ueber Ocoya auf allen konfigurierten Plattformen veroeffentlicht
4. Der Ausgang wird per Telegram bestaetigt
"""
import html
import os
import sys

from generate_post import generate_post
from ocoya_client import OcoyaClient
from telegram_bot import TelegramBot, approval_keyboard

MAX_REGENERATIONS = int(os.environ.get("MAX_REGENERATIONS", "4"))
POLL_TIMEOUT_MINUTES = int(os.environ.get("POLL_TIMEOUT_MINUTES", "60"))
REGENERATE_FEEDBACK = (
    "Bitte eine spuerbar andere Variante erstellen: anderer Blickwinkel, "
    "andere Formulierung, ggf. anderes Unterthema."
)


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


def _social_profile_ids() -> list:
    raw = os.environ["OCOYA_SOCIAL_PROFILE_IDS"]
    return [pid.strip() for pid in raw.split(",") if pid.strip()]


def main() -> int:
    bot = TelegramBot()

    try:
        draft = generate_post()
    except Exception as exc:
        bot.send_message(f"🚨 <b>Fehler bei der Post-Generierung:</b>\n{html.escape(str(exc))}")
        raise

    message_id = bot.send_message(_format_message(draft), reply_markup=approval_keyboard())

    regenerations = 0
    while True:
        timeout_seconds = POLL_TIMEOUT_MINUTES * 60
        decision = bot.wait_for_decision(message_id, timeout_seconds=timeout_seconds)

        if decision is None:
            bot.edit_message(
                message_id,
                _format_message(draft) + "\n\n⏱ <b>Zeitlimit erreicht - kein Post veroeffentlicht.</b>",
            )
            print("Timeout erreicht, kein Post veroeffentlicht.")
            return 0

        if decision == "cancel":
            bot.edit_message(
                message_id,
                _format_message(draft) + "\n\n❌ <b>Abgebrochen - kein Post veroeffentlicht.</b>",
            )
            print("Vom Nutzer abgebrochen.")
            return 0

        if decision == "regenerate":
            regenerations += 1
            if regenerations > MAX_REGENERATIONS:
                bot.edit_message(
                    message_id,
                    _format_message(draft) + "\n\n⚠️ <b>Limit fuer Neu-Generierungen erreicht.</b>",
                )
                print("Regenerations-Limit erreicht.")
                return 0
            bot.edit_message(message_id, _format_message(draft) + "\n\n⏳ Neuer Entwurf wird erstellt ...")
            draft = generate_post(feedback=REGENERATE_FEEDBACK)
            bot.edit_message(message_id, _format_message(draft), reply_markup=approval_keyboard())
            continue

        if decision == "approve":
            bot.edit_message(message_id, _format_message(draft) + "\n\n⏳ Wird veroeffentlicht ...")
            caption_with_tags = draft["caption"] + "\n\n" + " ".join(
                f"#{tag.lstrip('#')}" for tag in draft["hashtags"]
            )
            try:
                OcoyaClient().create_and_publish(caption_with_tags, _social_profile_ids())
            except Exception as exc:
                bot.edit_message(
                    message_id,
                    _format_message(draft) + f"\n\n🚨 <b>Fehler beim Veroeffentlichen:</b>\n{html.escape(str(exc))}",
                )
                raise
            bot.edit_message(
                message_id,
                _format_message(draft) + "\n\n✅ <b>Veroeffentlicht!</b>",
            )
            print("Post erfolgreich veroeffentlicht.")
            return 0

        # Unknown callback data - ignore and keep waiting.


if __name__ == "__main__":
    sys.exit(main())

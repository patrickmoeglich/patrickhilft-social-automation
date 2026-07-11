"""Orchestriert den taeglichen, vollautomatischen Social-Media-Post fuer den
Kanal "Zwischen den Zeilen" (kein Freigabeschritt - direkte Plattform-APIs):

1. Claude generiert die Geschichte (Thema/Caption/Hashtags) + die Hook-Frage
   fuer die Bildkarte
2. card_gen rendert die feste Story-Karte (identisches Design, wechselnder
   Text), gehostet auf ImgBB
3. Jedes in ENABLED_PLATFORMS aktivierte Ziel wird direkt ueber die jeweilige
   Plattform-API gepostet. Ein einzelner Plattform-Fehler stoppt NICHT die anderen.
4. Ergebnis-Zusammenfassung per Telegram (falls konfiguriert) und stdout.

Video-Ziele (Reels/TikTok) sind fuer den Kartenkanal nicht konfiguriert.
"""
import argparse
import html
import sys
import traceback
import os

from generate_content import generate_daily_content
import card_gen
import imgbb_client
from publishers import meta, linkedin, twitter, tiktok
import notify

VIDEO_TARGETS = {"instagram_reel", "facebook_video", "linkedin_video", "twitter_video", "tiktok"}
VALID_TARGETS = {
    "instagram_feed", "instagram_reel",
    "facebook_feed", "facebook_video",
    "linkedin", "linkedin_video",
    "twitter", "twitter_video",
    "tiktok",
}
ERROR_TEXT_LIMIT = 500


def _enabled_targets() -> list:
    raw = os.environ["ENABLED_PLATFORMS"]
    targets = [t.strip() for t in raw.split(",") if t.strip()]
    if not targets:
        raise RuntimeError("ENABLED_PLATFORMS ist leer - mindestens ein Ziel angeben.")
    unknown = set(targets) - VALID_TARGETS
    if unknown:
        raise RuntimeError(f"Unbekannte ENABLED_PLATFORMS-Eintraege: {sorted(unknown)}. Gueltig: {sorted(VALID_TARGETS)}")
    return targets


def _caption_with_tags(content: dict) -> str:
    return content["caption"] + "\n\n" + " ".join(f"#{tag.lstrip('#')}" for tag in content["hashtags"])


def _publish(target: str, caption: str, image: dict, video: dict) -> dict:
    if target == "instagram_feed":
        return meta.publish_instagram_image(image["url"], caption)
    if target == "instagram_reel":
        return meta.publish_instagram_reel(video["url"], caption)
    if target == "facebook_feed":
        return meta.publish_facebook_image(image["url"], caption)
    if target == "facebook_video":
        return meta.publish_facebook_video(video["url"], caption)
    if target == "linkedin":
        return linkedin.publish_image(image["bytes"], caption)
    if target == "linkedin_video":
        return linkedin.publish_video(video["bytes"], caption)
    if target == "twitter":
        return twitter.publish_image(image["bytes"], caption)
    if target == "twitter_video":
        return twitter.publish_video(video["bytes"], caption)
    if target == "tiktok":
        return tiktok.publish_video(video["url"], caption)
    raise RuntimeError(f"Unbekanntes Ziel: {target}")


def _format_summary(topic: str, results: dict) -> str:
    lines = [f"<b>Täglicher Post: {html.escape(topic)}</b>"]
    for target, (status, detail) in results.items():
        if status == "ok":
            lines.append(f"✅ {html.escape(target)}")
        else:
            detail_text = html.escape(str(detail))[:ERROR_TEXT_LIMIT]
            lines.append(f"🚨 {html.escape(target)}: {detail_text}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Generiert Text/Bild/Video, postet aber nirgendwo.")
    args = parser.parse_args()

    targets = _enabled_targets()
    if VIDEO_TARGETS & set(targets):
        raise RuntimeError(
            f"Video-Ziele {sorted(VIDEO_TARGETS & set(targets))} sind fuer den "
            "Kartenkanal nicht konfiguriert - nur Bild-Ziele aktivieren."
        )

    print("Generiere Geschichte + Karten-Frage ...")
    content = generate_daily_content()
    caption = _caption_with_tags(content)
    print(f"Thema: {content['topic']}")

    print("Rendere Bildkarte ...")
    card_bytes = card_gen.render_card(content["card_question"])
    primary_image = {"bytes": card_bytes, "url": imgbb_client.upload(card_bytes)}
    video = None

    if args.dry_run:
        print("\n--dry-run: es wird NICHT gepostet.\n")
        print(caption)
        print(f"\nKarten-Frage: {content['card_question']}")
        print(f"Bild-URL: {primary_image['url']}")
        print(f"Aktivierte Ziele (werden NICHT angesprochen): {targets}")
        return 0

    results = {}
    for target in targets:
        try:
            results[target] = ("ok", _publish(target, caption, primary_image, video))
            print(f"[OK] {target}")
        except Exception as exc:
            results[target] = ("error", str(exc))
            print(f"[FEHLER] {target}: {exc}")
            traceback.print_exc()

    notify.send(_format_summary(content["topic"], results))

    if any(status == "error" for status, _ in results.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

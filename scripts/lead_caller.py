"""Schickt die naechsten anrufbaren Leads als Telegram-Karten mit Gespraechsleitfaden.

Pro Lauf hoechstens `--limit` (Default 5) Betriebe - eine Liste mit 40 Eintraegen wird nicht
abtelefoniert, sondern weggeklickt. Ausgewaehlt werden Leads mit Status 'neu' oder faelliger
Wiedervorlage, die eine Telefonnummer haben; 'kein_interesse' bleibt dauerhaft gesperrt.

Jede Karte enthaelt Firma/Ort/Nummer, den vierteiligen Leitfaden und vier Buttons
(Erreicht / Nicht erreicht / Kein Interesse / Spaeter). Den Rueckschrieb der Klicks in den
Status uebernimmt der getrennte Poller (scripts/lead_status_poller.py) - dieses Skript
sendet nur und wartet nicht.

Nutzung:
    python scripts/lead_caller.py                 # bis zu 5 Karten senden
    python scripts/lead_caller.py --limit 3
    python scripts/lead_caller.py --dry-run       # Leitfaeden nur anzeigen, nichts senden
"""
import argparse
import html
import re
import sys
from pathlib import Path

import lead_finder
import lead_store
from telegram_bot import TelegramBot


def call_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Erreicht", "callback_data": "lead:erreicht"},
                {"text": "📵 Nicht erreicht", "callback_data": "lead:nicht_erreicht"},
            ],
            [
                {"text": "🚫 Kein Interesse", "callback_data": "lead:kein_interesse"},
                {"text": "🕘 Später", "callback_data": "lead:spaeter"},
            ],
        ]
    }


def _md_bold_to_html(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def format_card(row: dict, guide: str) -> str:
    """Baut den HTML-Text einer Anruf-Karte (Telegram parse_mode=HTML)."""
    esc = html.escape
    meta = " · ".join(part for part in (esc(row.get("region", "")), esc(row.get("industry", ""))) if part)
    phone = row.get("phone", "").strip()
    phone_line = f"☎ <b>{esc(phone)}</b>" if phone else "☎ <i>keine Nummer hinterlegt</i>"
    contact = row.get("contact_name", "").strip()
    lines = [f"<b>{esc(row.get('name', ''))}</b>"]
    if meta:
        lines.append(meta)
    lines.append(phone_line)
    if contact:
        lines.append(f"Ansprechpartner: {esc(contact)}")
    lines.append("")
    lines.append(_md_bold_to_html(esc(guide)))
    return "\n".join(lines)


def _pick_callable(rows: dict, limit: int) -> list:
    """Anrufbare Leads mit Telefonnummer, hoechster Score zuerst, auf `limit` gekappt."""
    ranked = lead_store.selectable(rows, lead_store.today(), limit=10_000)
    with_phone = [row for row in ranked if row.get("phone", "").strip()]
    return with_phone[:limit]


def run(store_path: Path, limit: int, dry_run: bool) -> int:
    rows = lead_store.load(store_path)
    leads = _pick_callable(rows, limit)
    if not leads:
        print("Keine anrufbaren Leads mit Telefonnummer offen.")
        return 0

    voice_profile = lead_finder.load_voice_profile()
    bot = None if dry_run else TelegramBot()
    sent = 0

    for row in leads:
        guide = lead_finder.generate_call_guide(
            name=row.get("name", ""), industry=row.get("industry", ""),
            region=row.get("region", ""), contact_name=row.get("contact_name", ""),
            befund=row.get("befund", ""), voice_profile=voice_profile,
        )
        row["guide"] = guide
        card = format_card(row, guide)
        if dry_run:
            print("=" * 60)
            print(card)
            continue
        message_id = bot.send_message(card, reply_markup=call_keyboard())
        lead_store.mark_sent(row, message_id)
        sent += 1
        print(f"Gesendet: {row.get('name', '')} (message_id {message_id})")

    if dry_run:
        print(f"\n[dry-run] {len(leads)} Leitfaden(e) erzeugt, nichts gesendet, Store unveraendert.")
    else:
        lead_store.save(store_path, rows)
        print(f"\n{sent} Anruf-Karte(n) nach Telegram geschickt. Klicks holt der Poller nach.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, default=lead_finder.DEFAULT_STORE,
                        help=f"Pfad der Master-Liste (Default: {lead_finder.DEFAULT_STORE})")
    parser.add_argument("--limit", type=int, default=5, help="Max. Anzahl Karten pro Lauf (Default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Leitfaeden erzeugen und anzeigen, aber nicht senden und Store nicht aendern")
    args = parser.parse_args()
    return run(args.store, args.limit, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())

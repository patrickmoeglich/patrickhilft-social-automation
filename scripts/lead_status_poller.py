"""Holt die Telegram-Button-Klicks der Anruf-Karten nach und schreibt sie in den Status zurueck.

Getrennt vom Sender (scripts/lead_caller.py): Patrick klickt ueber den Tag verteilt, nicht sofort.
Dieser Poller liest neue Updates (getUpdates), ordnet jeden Klick ueber die message_id dem Lead zu,
setzt den Status (Erreicht/Nicht erreicht/Kein Interesse/Spaeter) und entfernt die Buttons.

Der Update-Offset wird in leads/.tg_offset gemerkt, damit dieselben Klicks nicht doppelt
verarbeitet werden. Der gleiche Bot bedient auch die Content-Pipeline - fremde Updates (andere
Callback-Daten, Fotos) werden bestaetigt/ignoriert.

Nutzung:
    python scripts/lead_status_poller.py            # einmal alle offenen Klicks abarbeiten
    python scripts/lead_status_poller.py --watch 300 # 5 Minuten lang lauschen
"""
import argparse
import sys
import time
from pathlib import Path

import lead_finder
import lead_store
from lead_caller import format_card
from telegram_bot import TelegramBot

STATUS_LABELS = {
    lead_store.STATUS_ANGERUFEN: "✅ Erreicht / angerufen",
    lead_store.STATUS_NICHT_ERREICHT: "📵 Nicht erreicht – Wiedervorlage in 2 Tagen",
    lead_store.STATUS_KEIN_INTERESSE: "🚫 Kein Interesse – dauerhaft gesperrt",
    lead_store.STATUS_WIEDERVORLAGE: "🕘 Später – Wiedervorlage in 7 Tagen",
}


def _offset_path(store_path: Path) -> Path:
    return Path(store_path).parent / ".tg_offset"


def _read_offset(store_path: Path) -> int:
    path = _offset_path(store_path)
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (ValueError, OSError):
        return 0


def _write_offset(store_path: Path, offset: int) -> None:
    path = _offset_path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(offset), encoding="utf-8")


def _handle_callback(bot: TelegramBot, rows: dict, callback: dict) -> bool:
    """Verarbeitet ein callback_query. Gibt True zurueck, wenn ein Lead-Status geaendert wurde."""
    data = callback.get("data", "")
    callback_id = callback["id"]
    if not data.startswith("lead:"):
        bot._ack_callback(callback_id)  # gehoert nicht zur Anrufliste (z.B. Content-Pipeline)
        return False

    action = data.split(":", 1)[1]
    if action not in lead_store.BUTTON_ACTIONS:
        bot._ack_callback(callback_id)
        return False

    message_id = callback.get("message", {}).get("message_id")
    row = lead_store.find_by_message_id(rows, message_id)
    if row is None:
        # Karte nicht (mehr) zuordenbar - evtl. schon abgearbeitet oder aus altem Lauf.
        _try_answer(bot, callback_id, "Schon abgearbeitet oder nicht mehr zugeordnet.")
        return False

    name = row.get("name", "")
    guide = row.get("guide", "")
    new_status = lead_store.apply_action(row, action, lead_store.today())
    label = STATUS_LABELS.get(new_status, new_status)

    _try_answer(bot, callback_id, f"Notiert: {label}")
    try:
        footer = f"\n\n— <b>{label}</b> ({lead_store.today().isoformat()})"
        bot.edit_message(message_id, format_card(row, guide) + footer, reply_markup=None)
    except RuntimeError:
        pass  # Nachricht evtl. zu alt zum Editieren - Status ist trotzdem gesetzt
    print(f"{name}: {new_status}")
    return True


def _try_answer(bot: TelegramBot, callback_id: str, text: str) -> None:
    try:
        bot.answer_callback_query(callback_id, text=text)
    except RuntimeError:
        pass  # Query evtl. abgelaufen - unkritisch


def _drain_once(bot: TelegramBot, rows: dict, offset: int, poll_timeout: int) -> tuple:
    """Ein getUpdates-Aufruf. Gibt (neuer_offset, anzahl_updates, anzahl_aenderungen) zurueck."""
    updates = bot.get_updates(offset=offset, timeout=poll_timeout)
    changes = 0
    for update in updates:
        offset = update["update_id"] + 1
        callback = update.get("callback_query")
        if callback:
            changes += _handle_callback(bot, rows, callback)
    return offset, len(updates), changes


def run(store_path: Path, watch_seconds: int) -> int:
    rows = lead_store.load(store_path)
    bot = TelegramBot()
    offset = _read_offset(store_path)
    total_changes = 0

    if watch_seconds > 0:
        deadline = time.monotonic() + watch_seconds
        while time.monotonic() < deadline:
            poll_timeout = int(min(25, max(1, deadline - time.monotonic())))
            offset, _, changes = _drain_once(bot, rows, offset, poll_timeout)
            if changes:
                lead_store.save(store_path, rows)
                _write_offset(store_path, offset)
                total_changes += changes
            else:
                _write_offset(store_path, offset)
    else:
        # Einmalig: alle aktuell anstehenden Updates abarbeiten, dann beenden.
        while True:
            offset, count, changes = _drain_once(bot, rows, offset, poll_timeout=1)
            total_changes += changes
            if changes:
                lead_store.save(store_path, rows)
            _write_offset(store_path, offset)
            if count == 0:
                break

    print(f"Fertig. {total_changes} Status-Aenderung(en).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, default=lead_finder.DEFAULT_STORE,
                        help=f"Pfad der Master-Liste (Default: {lead_finder.DEFAULT_STORE})")
    parser.add_argument("--watch", type=int, default=0, metavar="SEKUNDEN",
                        help="So lange lauschen (Default: 0 = einmal abarbeiten und beenden)")
    args = parser.parse_args()
    return run(args.store, args.watch)


if __name__ == "__main__":
    sys.exit(main())

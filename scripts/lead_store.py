"""Persistente Master-Liste der Leads (leads/leads.csv).

Eine Datei ist die einzige Quelle der Wahrheit fuer Status und Anruf-Historie und ueber
alle Laeufe hinweg stabil. Schluessel ist die normalisierte Website (Fallback: Name).

Wichtig fachlich: `kein_interesse` ist eine dauerhafte Sperre. Wer einmal abgelehnt hat,
darf NICHT erneut auf der Anrufliste erscheinen - genau hier verlaeuft die Grenze von
zulaessiger Ansprache zu Belaestigung (vgl. mutmassliche Einwilligung, § 7 UWG).

Diese Datei enthaelt personenbezogene Kontaktdaten und ist per .gitignore vom Commit
ausgenommen (nur leads/prospects.example.csv wird versioniert).
"""
import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

FIELDNAMES = [
    "name", "website", "industry", "region", "contact_name", "phone",
    "score", "befund", "guide",
    "status", "angerufen_am", "notiz", "wiedervorlage_am",
    "tg_message_id", "updated_am",
]

STATUS_NEU = "neu"
STATUS_ANGERUFEN = "angerufen"
STATUS_NICHT_ERREICHT = "nicht_erreicht"
STATUS_WIEDERVORLAGE = "wiedervorlage"
STATUS_KEIN_INTERESSE = "kein_interesse"
STATUS_TERMIN = "termin"

# Telegram-Button-Aktion -> (neuer Status, Wiedervorlage in Tagen | None).
# None bei kein_interesse (dauerhafte Sperre) und erreicht (abgeschlossen, kein Auto-Recall).
BUTTON_ACTIONS = {
    "erreicht": (STATUS_ANGERUFEN, None),
    "nicht_erreicht": (STATUS_NICHT_ERREICHT, 2),
    "kein_interesse": (STATUS_KEIN_INTERESSE, None),
    "spaeter": (STATUS_WIEDERVORLAGE, 7),
}


def normalize_key(website: str, name: str = "") -> str:
    key = (website or "").strip().lower()
    key = re.sub(r"^https?://", "", key)
    key = re.sub(r"^www\.", "", key)
    key = key.rstrip("/")
    return key or (name or "").strip().lower()


def today() -> date:
    return datetime.now().date()


def load(path: Path) -> Dict[str, dict]:
    """Laedt die Master-Liste als {key: row}; fehlende Spalten werden auf "" gesetzt."""
    rows: Dict[str, dict] = {}
    path = Path(path)
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            normalized = {fn: (row.get(fn) or "") for fn in FIELDNAMES}
            key = normalize_key(normalized["website"], normalized["name"])
            if key:
                rows[key] = normalized
    return rows


def save(path: Path, rows: Dict[str, dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows.values():
            writer.writerow({fn: row.get(fn, "") for fn in FIELDNAMES})


def upsert_research(rows: Dict[str, dict], *, name: str, website: str, industry: str,
                    region: str, contact_name: str, phone: str, score: int, befund: str) -> str:
    """Fuegt einen recherchierten Lead ein oder frischt die Recherche-Felder eines bestehenden auf.

    Ein bestehender Lead wird NIE in den Status zurueckgesetzt (sonst wuerde z.B. ein
    'kein_interesse' beim naechsten Recherchelauf wieder zu 'neu'). Nur die reinen
    Recherche-Felder (Befund/Score/Kontaktdaten) werden aktualisiert.
    Gibt "neu" oder "aktualisiert" zurueck.
    """
    key = normalize_key(website, name)
    existing = rows.get(key)
    if existing is None:
        rows[key] = {
            "name": name, "website": website, "industry": industry, "region": region,
            "contact_name": contact_name, "phone": phone, "score": str(score),
            "befund": befund, "guide": "", "status": STATUS_NEU,
            "angerufen_am": "", "notiz": "", "wiedervorlage_am": "",
            "tg_message_id": "", "updated_am": today().isoformat(),
        }
        return "neu"

    existing["industry"] = industry or existing["industry"]
    existing["region"] = region or existing["region"]
    existing["contact_name"] = contact_name or existing["contact_name"]
    existing["phone"] = phone or existing["phone"]
    existing["score"] = str(score)
    existing["befund"] = befund
    existing["updated_am"] = today().isoformat()
    return "aktualisiert"


def _is_due(row: dict, ref: date) -> bool:
    raw = (row.get("wiedervorlage_am") or "").strip()
    if not raw:
        return True
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date() <= ref
    except ValueError:
        return True


def selectable(rows: Dict[str, dict], ref: date, limit: int) -> list:
    """Leads, die (erneut) angerufen werden duerfen, nach Score sortiert, auf `limit` gekappt.

    Auswahl = Status 'neu' ODER faellige Wiedervorlage/Nicht-erreicht - und jeweils nur,
    wenn KEINE Telegram-Karte offen ist (tg_message_id leer). 'kein_interesse', 'angerufen'
    und 'termin' werden nie automatisch erneut vorgelegt.
    """
    candidates = []
    for row in rows.values():
        if row.get("tg_message_id", "").strip():
            continue  # bereits als Karte offen (in Bearbeitung) - nicht doppelt schicken
        status = row.get("status", "")
        if status == STATUS_NEU:
            candidates.append(row)
        elif status in (STATUS_WIEDERVORLAGE, STATUS_NICHT_ERREICHT) and _is_due(row, ref):
            candidates.append(row)
    candidates.sort(key=lambda r: _as_int(r.get("score")), reverse=True)
    return candidates[:limit]


def find_by_message_id(rows: Dict[str, dict], message_id) -> Optional[dict]:
    target = str(message_id)
    for row in rows.values():
        if str(row.get("tg_message_id", "")).strip() == target:
            return row
    return None


def apply_action(row: dict, action: str, ref: date) -> str:
    """Wendet eine Button-Aktion auf einen Lead an und gibt den neuen Status zurueck.

    Setzt tg_message_id zurueck (die Karte ist abgearbeitet), damit eine faellige
    Wiedervorlage den Lead spaeter erneut vorlegen kann.
    """
    status, wv_days = BUTTON_ACTIONS[action]
    row["status"] = status
    if action in ("erreicht", "nicht_erreicht"):
        row["angerufen_am"] = ref.isoformat()
    row["wiedervorlage_am"] = (ref + timedelta(days=wv_days)).isoformat() if wv_days is not None else ""
    row["tg_message_id"] = ""
    row["updated_am"] = ref.isoformat()
    return status


def mark_sent(row: dict, message_id) -> None:
    row["tg_message_id"] = str(message_id)
    row["updated_am"] = today().isoformat()


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

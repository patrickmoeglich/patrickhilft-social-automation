"""Gedaechtnis und Telegram-Versand fuer den woechentlichen Tool-Radar.

Der Radar sucht neue MCP-Server, Claude Skills und vergleichbare Erweiterungen.
Die Recherche und die Nutzwert-Bewertung macht Claude Code (Skill "tool-radar"),
weil das ein Urteil ist und kein Scraping-Problem. Dieses Modul haelt nur die
beiden Teile, die deterministisch sein muessen:

1. Das Gedaechtnis (tool-radar-gesehen.json): Was wurde schon gemeldet, mit
   welchem Stand und welcher Bewertung. Ohne diese Datei wuerde jeder Lauf
   dieselben Tools erneut melden.
2. Der Versand: Telegram bricht Nachrichten ueber 4096 Zeichen hart ab, deshalb
   wird am Absatz getrennt statt mitten im Satz.

Aufruf:
    python scripts/tool_radar.py status
    python scripts/tool_radar.py senden < report.txt
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO_WURZEL = Path(__file__).resolve().parent.parent
GEDAECHTNIS_PFAD = REPO_WURZEL / "tool-radar-gesehen.json"
ENV_PFAD = REPO_WURZEL / ".env"

# Telegram-Limit ist 4096 Zeichen; etwas Luft fuer den Teil-Zaehler im Header.
TELEGRAM_MAX_ZEICHEN = 3900

SCHEMA_VERSION = 1

# Ergebnis von pruefe(): steuert, ob ein Kandidat in den Report kommt.
NEU = "neu"
UPDATE = "update"
BEKANNT = "bekannt"

# status-Feld im Gedaechtnis.
STATUS_GEMELDET = "gemeldet"
STATUS_ZU_SCHWACH = "zu_schwach"
STATUS_AUSGESCHLOSSEN = "ausgeschlossen"

# Ein bereits verworfener Kandidat wird bei neuem Stand erneut bewertet - ein
# Tool, das vor einem Jahr eine Spielerei war, kann heute brauchbar sein.
STATUS_NEU_BEWERTBAR = (STATUS_ZU_SCHWACH, STATUS_AUSGESCHLOSSEN)


def heute() -> str:
    return datetime.now().date().isoformat()


def schluessel(name: str, quelle: str) -> str:
    """Stabiler Schluessel: Gross-/Kleinschreibung und Randleerzeichen ignorieren."""
    return f"{(name or '').strip().lower()}|{(quelle or '').strip().lower()}"


def laden(pfad: Path = GEDAECHTNIS_PFAD) -> dict:
    """Laedt das Gedaechtnis; eine fehlende Datei ist der normale Erstlauf."""
    pfad = Path(pfad)
    if not pfad.exists():
        return {"version": SCHEMA_VERSION, "letzter_lauf": None, "eintraege": []}
    with pfad.open(encoding="utf-8") as datei:
        daten = json.load(datei)
    daten.setdefault("version", SCHEMA_VERSION)
    daten.setdefault("letzter_lauf", None)
    daten.setdefault("eintraege", [])
    return daten


def speichern(daten: dict, pfad: Path = GEDAECHTNIS_PFAD) -> None:
    daten["letzter_lauf"] = heute()
    pfad = Path(pfad)
    pfad.write_text(
        json.dumps(daten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _index(daten: dict) -> Dict[str, dict]:
    return {schluessel(e.get("name", ""), e.get("quelle", "")): e for e in daten["eintraege"]}


def pruefe(daten: dict, name: str, quelle: str, stand: Optional[str] = None) -> str:
    """Ist der Kandidat neu, ein Update oder laengst bekannt?

    `stand` ist das Datum des letzten Commits/Releases (ISO, z. B. "2026-07-14").
    ISO-Datumsstrings sind lexikografisch vergleichbar, deshalb reicht ">".
    """
    eintrag = _index(daten).get(schluessel(name, quelle))
    if eintrag is None:
        return NEU

    # Dauersperre schlaegt alles: ein bewusst und dauerhaft verworfenes Tool
    # darf auch nach einem neuen Release nicht wieder auftauchen. Analog zu
    # STATUS_KEIN_INTERESSE in lead_store.py.
    if eintrag.get("dauersperre"):
        return BEKANNT

    alter_stand = eintrag.get("stand") or ""
    hat_neuen_stand = bool(stand) and stand > alter_stand
    if not hat_neuen_stand:
        return BEKANNT
    if eintrag.get("status") in STATUS_NEU_BEWERTBAR:
        return NEU
    return UPDATE


def merke(
    daten: dict,
    name: str,
    quelle: str,
    url: str = "",
    stand: str = "",
    bewertung: int = 0,
    cluster: Optional[List[str]] = None,
    status: str = STATUS_GEMELDET,
    notiz: str = "",
    dauersperre: bool = False,
) -> dict:
    """Legt einen Kandidaten ab oder aktualisiert ihn. Gibt das Gedaechtnis zurueck.

    Auch verworfene Kandidaten werden gespeichert - sonst wird jede Woche
    dieselbe Enttaeuschung neu recherchiert und neu bewertet.

    `dauersperre=True` heisst: nie wieder melden, auch nicht nach einem neuen
    Release. Fuer Tools, die Patrick bewusst und endgueltig abgelehnt hat.
    """
    eintrag = {
        "name": name,
        "quelle": quelle,
        "url": url,
        "datum": heute(),
        "stand": stand,
        "bewertung": bewertung,
        "cluster": cluster or [],
        "status": status,
        "notiz": notiz,
        "dauersperre": dauersperre,
    }
    key = schluessel(name, quelle)
    daten["eintraege"] = [
        e for e in daten["eintraege"] if schluessel(e.get("name", ""), e.get("quelle", "")) != key
    ]
    daten["eintraege"].append(eintrag)
    return daten


def teile(text: str, grenze: int = TELEGRAM_MAX_ZEICHEN) -> List[str]:
    """Zerlegt den Report in Telegram-taugliche Stuecke, bevorzugt am Absatz.

    Ein Absatz, der allein schon zu lang ist, wird hart geschnitten - besser ein
    haesslicher Umbruch als eine von Telegram abgeschnittene Nachricht.
    """
    text = text.strip()
    if len(text) <= grenze:
        return [text] if text else []

    stuecke: List[str] = []
    rest = text
    while len(rest) > grenze:
        schnitt = rest.rfind("\n\n", 0, grenze)
        if schnitt <= 0:
            schnitt = rest.rfind("\n", 0, grenze)
        if schnitt <= 0:
            schnitt = grenze
        stuecke.append(rest[:schnitt].strip())
        rest = rest[schnitt:].strip()
    if rest:
        stuecke.append(rest)
    return [s for s in stuecke if s]


def lade_env(pfad: Path = ENV_PFAD) -> int:
    """Traegt fehlende Werte aus .env in os.environ nach; gibt deren Anzahl zurueck.

    Das uebrige Repo erwartet, dass der Aufrufer die .env vorher exportiert
    (siehe README). Fuer den Montagslauf aus der Aufgabenplanung gibt es keinen
    solchen Aufrufer - ohne das hier scheitert der Lauf um 07:00 still an einem
    KeyError. Bereits gesetzte Variablen haben Vorrang, damit eine echte
    Umgebungsvariable die Datei weiterhin ueberschreiben kann.
    """
    pfad = Path(pfad)
    if not pfad.exists():
        return 0

    nachgetragen = 0
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        name, _, wert = zeile.partition("=")
        name = name.strip()
        if name in os.environ:
            continue
        os.environ[name] = wert.strip().strip('"').strip("'")
        nachgetragen += 1
    return nachgetragen


def _beispielwerte(pfad: Optional[Path] = None) -> Dict[str, str]:
    """Liest .env.example, um echte Werte von den Platzhaltern zu unterscheiden."""
    pfad = Path(pfad) if pfad else REPO_WURZEL / ".env.example"
    werte: Dict[str, str] = {}
    if not pfad.exists():
        return werte
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if zeile and not zeile.startswith("#") and "=" in zeile:
            name, _, wert = zeile.partition("=")
            werte[name.strip()] = wert.strip().strip('"').strip("'")
    return werte


def pruefe_zugangsdaten(beispiel_pfad: Optional[Path] = None) -> Optional[str]:
    """Prueft die Telegram-Zugangsdaten und benennt das Problem konkret.

    Unterscheidet drei Faelle, weil sie unterschiedliche Handgriffe erfordern:
    fehlt (nichts eingetragen), Platzhalter (Beispielwert stehen geblieben),
    ungueltiges Format (etwas eingetragen, aber strukturell falsch).

    Gibt niemals den Wert selbst aus - nur Laengen und Strukturaussagen. Die
    Meldung landet in logs/tool-radar.log, und dort hat ein Bot-Token nichts
    verloren.

    Bewusst nachsichtig beim Format: das Geheimnis nach dem ersten Doppelpunkt
    darf selbst Doppelpunkte enthalten und in der Laenge variieren. Eine zu
    strenge Pruefung wuerde gueltige Token abweisen und den Montagslauf grundlos
    stoppen - schaedlicher als ein durchgelassener Tippfehler, den Telegram
    ohnehin mit HTTP 401 quittiert.
    """
    fehlend = [n for n in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID") if not os.environ.get(n)]
    if fehlend:
        return (
            f"Zugangsdaten fehlen: {', '.join(fehlend)}. "
            "In .env eintragen (Token von @BotFather)."
        )

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    beispiel = _beispielwerte(beispiel_pfad)

    for name, wert in (("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)):
        if beispiel.get(name) is not None and wert == beispiel[name]:
            return (
                f"{name} ist noch der Beispielwert aus .env.example. "
                "Echten Wert eintragen."
            )

    if ":" not in token:
        return (
            "TELEGRAM_BOT_TOKEN hat ein ungueltiges Format: kein Doppelpunkt "
            f"enthalten (Laenge {len(token)}). Erwartet wird <Bot-ID>:<Geheimnis>."
        )

    bot_id, _, geheimnis = token.partition(":")
    if not bot_id.isdigit():
        return (
            "TELEGRAM_BOT_TOKEN hat ein ungueltiges Format: der Teil vor dem "
            f"ersten Doppelpunkt ist nicht rein numerisch (Laenge {len(bot_id)}). "
            "Dort wird die Bot-ID erwartet."
        )
    if len(geheimnis) < 20:
        return (
            "TELEGRAM_BOT_TOKEN hat ein ungueltiges Format: der Teil nach dem "
            f"ersten Doppelpunkt ist nur {len(geheimnis)} Zeichen lang, "
            "erwartet werden mindestens 20."
        )

    if not re.fullmatch(r"-?\d+", chat_id):
        return (
            "TELEGRAM_CHAT_ID hat ein ungueltiges Format: keine ganze Zahl "
            f"(Laenge {len(chat_id)}). Gruppen-IDs beginnen mit einem Minus."
        )
    return None


def sende(text: str, bot=None) -> List[int]:
    """Schickt den Report als reinen Text (keine HTML-Escaping-Fallen bei URLs)."""
    if bot is None:
        lade_env()
        problem = pruefe_zugangsdaten()
        if problem:
            raise RuntimeError(f"Telegram-Versand nicht moeglich. {problem}")
        from telegram_bot import TelegramBot

        bot = TelegramBot()

    stuecke = teile(text)
    gesamt = len(stuecke)
    ids = []
    for nummer, stueck in enumerate(stuecke, start=1):
        kopf = f"({nummer}/{gesamt})\n" if gesamt > 1 else ""
        ids.append(bot.send_message(kopf + stueck, parse_mode=None))
    return ids


def _status() -> None:
    daten = laden()
    gemeldet = [e for e in daten["eintraege"] if e.get("status") == STATUS_GEMELDET]
    print(f"Gedaechtnis: {GEDAECHTNIS_PFAD}")
    print(f"Letzter Lauf: {daten.get('letzter_lauf') or 'nie'}")
    print(f"Eintraege gesamt: {len(daten['eintraege'])} (davon gemeldet: {len(gemeldet)})")
    for eintrag in sorted(gemeldet, key=lambda e: -e.get("bewertung", 0))[:10]:
        print(f"  {eintrag.get('bewertung', 0):>2}/10  {eintrag.get('name')}  [{eintrag.get('quelle')}]")


def main(argv: List[str]) -> int:
    befehl = argv[1] if len(argv) > 1 else ""
    if befehl == "status":
        _status()
        return 0
    if befehl == "senden":
        text = sys.stdin.read()
        if not text.strip():
            print("Nichts zu senden (leere Eingabe).")
            return 1
        ids = sende(text)
        print(f"Gesendet: {len(ids)} Nachricht(en), IDs {ids}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

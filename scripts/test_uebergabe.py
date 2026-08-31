"""Pruefauftrag "Uebergabe" (Phase 7A) -- ohne Netz, ohne Telegram, ohne Ocoya.

**Attrappen statt Gegenstellen.** `uebergeben()` bekommt Bot und Ocoya-Client
hereingereicht; hier stehen zwei Attrappen, die mitschreiben, was sie bekommen
haetten. **Es geht keine Nachricht hinaus und es entsteht kein Entwurf.**

**Eigenstaendig und ohne pytest**, weil dieses Repo bisher keine Testdatei und
kein Testframework hat (`requirements.txt` fuehrt keines). Aufbau und
Ausgabeformat sind an die Pruefskripte von KZ-Privat angelehnt, damit beide
Seiten gleich zu lesen sind.

Starten:
    cd scripts && python test_uebergabe.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import List, Optional

from uebergabe import (
    EingabeFehler,
    caption_mit_tags,
    eingaben_lesen,
    ergebnis_schreiben,
    nachricht_bauen,
    profile_aufloesen,
    uebergeben,
)

bestanden = 0
funde: List[str] = []
GESAMT = 15


def pruefe(nummer: str, was: str, bedingung: bool, beleg: str) -> None:
    global bestanden
    if bedingung:
        bestanden += 1
        print(f"[pruef] {nummer} OK   {was}")
    else:
        funde.append(f"{nummer} {was} -- {beleg}")
        print(f"[pruef] {nummer} FUND {was}")
    print(f"[pruef]         {beleg}")


class BotAttrappe:
    """Schreibt mit, statt zu senden. `antworten` ist der Plan der Knopfdruecke."""

    def __init__(self, antworten: List[Optional[str]]):
        self.antworten = list(antworten)
        self.gesendet: List[str] = []
        self.wartezeiten: List[int] = []
        self.letzte_tastatur: Optional[dict] = None

    def send_message(self, text: str, reply_markup: Optional[dict] = None) -> int:
        self.gesendet.append(text)
        if reply_markup is not None:
            self.letzte_tastatur = reply_markup
        return 4711

    def wait_for_decision(self, message_id: int, timeout_seconds: int) -> Optional[str]:
        self.wartezeiten.append(timeout_seconds)
        return self.antworten.pop(0) if self.antworten else None


class OcoyaAttrappe:
    """Legt nichts an. Merkt sich, womit sie aufgerufen worden waere."""

    def __init__(self, antwort: Optional[dict] = None):
        self.antwort = antwort if antwort is not None else {"postGroupId": "cmtATTRAPPE0001"}
        self.entwuerfe: List[tuple] = []
        self.termine: List[tuple] = []

    def create_draft_post(self, caption, profil_ids, media_urls=None):
        self.entwuerfe.append((caption, list(profil_ids), list(media_urls or [])))
        return self.antwort

    def schedule_post(self, post_id, scheduled_at_iso):
        self.termine.append((post_id, scheduled_at_iso))
        return {"ok": True}


UMGEBUNG = {
    "KZ_BEITRAG_ID": "8",
    "CAPTION": "Hilfe im Alltag - ein Beispiel aus dieser Woche.",
    "HASHTAGS": "#pflege alltagshilfe",
    "BILD_URL": "https://cdn.example/bild-attrappe.png",
    "PLATTFORMEN": "facebook",
    "SCHEDULED_AT": "2026-09-02T10:00:00+02:00",
}

# Synthetische Profil-Attrappen. Es wird kein echtes Secret gelesen.
PROFILE = {
    "OCOYA_PROFIL_FACEBOOK": "profil-attrappe-1",
    "OCOYA_PROFIL_LINKEDIN": "profil-attrappe-2",
}


def main() -> int:
    print("\n[pruef] Uebergabe Phase 7A -- ohne Netz, ohne Telegram, ohne Ocoya.\n")

    # --- 1 bis 4: die Eingabepruefung ---------------------------------------
    e = eingaben_lesen(UMGEBUNG)
    pruefe(
        "1",
        "eine vollstaendige Eingabe wird gelesen, Hashtags ohne Raute und ohne Komma",
        e.kz_beitrag_id == "8"
        and e.hashtags == ["pflege", "alltagshilfe"]
        and e.plattformen == ["facebook"],
        f"id={e.kz_beitrag_id} tags={e.hashtags} plattformen={e.plattformen}",
    )

    faelle = {
        "Id keine Zahl": {**UMGEBUNG, "KZ_BEITRAG_ID": "acht"},
        "Caption leer": {**UMGEBUNG, "CAPTION": "   "},
        "Bild nicht https": {**UMGEBUNG, "BILD_URL": "http://cdn.example/x.png"},
        "Zeit ohne Versatz": {**UMGEBUNG, "SCHEDULED_AT": "2026-09-02T10:00:00"},
        "Zeit kein ISO": {**UMGEBUNG, "SCHEDULED_AT": "naechsten Dienstag"},
        "Plattform unbekannt": {**UMGEBUNG, "PLATTFORMEN": "mastodon"},
        "Plattformen leer": {**UMGEBUNG, "PLATTFORMEN": " "},
    }
    durchgelassen = []
    for name, u in faelle.items():
        try:
            eingaben_lesen(u)
            durchgelassen.append(f"{name}: DURCHGELASSEN")
        except EingabeFehler:
            pass
    pruefe(
        "2",
        "jede unbrauchbare Eingabe wird abgewiesen -- vor jedem Netzaufruf",
        not durchgelassen,
        "alle sieben Faelle abgewiesen" if not durchgelassen else " / ".join(durchgelassen),
    )

    ids = profile_aufloesen(["facebook"], PROFILE)
    pruefe(
        "3",
        "Plattformnamen werden aus Secrets zu Profil-IDs aufgeloest",
        ids == ["profil-attrappe-1"],
        f"{len(ids)} Profil(e) aufgeloest",
    )

    try:
        profile_aufloesen(["linkedin", "tiktok"], PROFILE)
        fehltext = "(kein Fehler!)"
        geklappt = False
    except EingabeFehler as f:
        fehltext = str(f)
        geklappt = "tiktok" in fehltext and "profil-attrappe" not in fehltext
    pruefe(
        "4",
        "fehlt ein Profil-Secret, nennt der Fehler die Plattform -- und keine ID",
        geklappt,
        fehltext,
    )

    # --- 5 und 6: die Nachricht ---------------------------------------------
    text = nachricht_bauen(e)
    pruefe(
        "5",
        "die Telegram-Nachricht traegt die KZ-Beitrags-ID sichtbar",
        "KZ-Beitrag 8" in text and "facebook" in text and "2026-09-02T10:00:00+02:00" in text,
        text.splitlines()[0],
    )
    ohne_id = "profil-attrappe" not in text
    pruefe(
        "6",
        "in der Nachricht steht keine Profil-ID",
        ohne_id,
        "keine ID in der Nachricht" if ohne_id else "ID DURCHGERUTSCHT",
    )

    # --- 7 und 8: der geglueckte Weg ----------------------------------------
    bot = BotAttrappe(["approve"])
    ocoya = OcoyaAttrappe()
    erg = uebergeben(bot, ocoya, e, ids, 3600)
    pruefe(
        "7",
        "nach Freigabe wird genau ein Entwurf angelegt und zum gelieferten Zeitpunkt eingeplant",
        erg.entscheidung == "freigegeben"
        and len(ocoya.entwuerfe) == 1
        and ocoya.entwuerfe[0][1] == ["profil-attrappe-1"]
        and ocoya.entwuerfe[0][2] == ["https://cdn.example/bild-attrappe.png"]
        and ocoya.termine == [("cmtATTRAPPE0001", "2026-09-02T10:00:00+02:00")],
        f"{erg.entscheidung}, {len(ocoya.entwuerfe)} Entwurf/Entwuerfe, Termin {ocoya.termine}",
    )
    pruefe(
        "8",
        "der Text geht mit Hashtags hinaus, so wie main.py ihn baut",
        ocoya.entwuerfe[0][0] == caption_mit_tags(e)
        and ocoya.entwuerfe[0][0].endswith("#pflege #alltagshilfe"),
        repr(ocoya.entwuerfe[0][0][-40:]),
    )

    # --- 9 und 10: Ablehnung und Zeitlimit ----------------------------------
    for nummer, plan, erwartet in (("9", ["cancel"], "abgelehnt"), ("10", [None], "zeitlimit")):
        b = BotAttrappe(plan)
        o = OcoyaAttrappe()
        r = uebergeben(b, o, e, ids, 3600)
        pruefe(
            nummer,
            f"bei Ausgang '{erwartet}' entsteht bei Ocoya NICHTS",
            r.entscheidung == erwartet
            and not o.entwuerfe
            and not o.termine
            and r.ocoya_post_group_id is None,
            f"{r.entscheidung}, {len(o.entwuerfe)} Entwurf/Entwuerfe, {len(o.termine)} Termin(e)",
        )

    # --- 11: die Tastatur kennt kein Neu-Generieren mehr --------------------
    #
    # Seit `7f5afe4` laesst sich der Knopf abschalten. Ihn wegzulassen ist
    # besser, als ihn zu erklaeren: Ein Knopf, der nur auf einen Hinweistext
    # fuehrt, ist ein Fehler im Dialog. Die frueheren Hinweisschleife und
    # HINWEISE_MAX sind damit entfallen.
    b = BotAttrappe(["approve"])
    o = OcoyaAttrappe()
    uebergeben(b, o, e, ids, 3600)
    tasten = [k["callback_data"] for reihe in b.letzte_tastatur["inline_keyboard"] for k in reihe]
    pruefe(
        "11",
        "die Freigabe-Tastatur bietet nur Freigeben und Abbrechen -- kein Neu-Generieren",
        tasten == ["approve", "cancel"],
        f"Tasten: {tasten}",
    )

    # --- 11b: eine unerwartete Rueckmeldung gilt als Ablehnung --------------
    #
    # Mit abgeschalteter Taste kann sie eigentlich nicht kommen. Kommt sie
    # doch, wird nichts angelegt und der Wortlaut festgehalten statt
    # verschwiegen.
    b = BotAttrappe(["regenerate"])
    o = OcoyaAttrappe()
    r = uebergeben(b, o, e, ids, 3600)
    pruefe(
        "11b",
        "eine unerwartete Rueckmeldung gilt als Ablehnung -- und wird vermerkt",
        r.entscheidung == "abgelehnt"
        and "regenerate" in r.hinweis
        and not o.entwuerfe
        and not o.termine,
        f"{r.entscheidung}, Hinweis: {r.hinweis!r}, {len(o.entwuerfe)} Entwurf/Entwuerfe",
    )

    # --- 12: das Ergebnisartefakt -------------------------------------------
    ziel = os.path.join(tempfile.mkdtemp(), "uebergabe-ergebnis.json")
    ergebnis_schreiben(erg, ziel)
    with open(ziel, encoding="utf-8") as datei:
        gelesen = json.load(datei)
    pruefe(
        "12",
        "das Artefakt traegt KZ-ID, Entscheidung, Ocoya-Id und Termin -- und keine Profil-ID",
        gelesen["kz_beitrag_id"] == "8"
        and gelesen["entscheidung"] == "freigegeben"
        and gelesen["ocoya_post_group_id"] == "cmtATTRAPPE0001"
        and gelesen["termin"] == "2026-09-02T10:00:00+02:00"
        and "profil-attrappe" not in json.dumps(gelesen),
        json.dumps(gelesen, ensure_ascii=False),
    )

    # --- 13 und 14: der optionale Zuordnungswert -------------------------
    #
    # **Reine Dokumentation.** Der genannte Entwurf wird nicht angefasst --
    # kein Loeschen, kein Einplanen, kein Aendern. Punkt 14 haelt das fest,
    # damit es niemand spaeter nur kurz ergaenzt.
    ALT_ID = "cmtfknq61000v04jq06dlb7wr"
    e2 = eingaben_lesen({**UMGEBUNG, "ERSETZT_OCOYA_GRUPPE_ID": ALT_ID})
    b2 = BotAttrappe(["approve"])
    o2 = OcoyaAttrappe()
    r2 = uebergeben(b2, o2, e2, ids, 3600)
    ziel2 = os.path.join(tempfile.mkdtemp(), "uebergabe-ergebnis.json")
    ergebnis_schreiben(r2, ziel2)
    with open(ziel2, encoding="utf-8") as datei:
        g2 = json.load(datei)
    pruefe(
        "13",
        "ersetzt_ocoya_gruppe_id wird uebernommen und steht im Artefakt",
        e2.ersetzt_ocoya_gruppe_id == ALT_ID and g2["ersetzt_ocoya_gruppe_id"] == ALT_ID,
        json.dumps(g2, ensure_ascii=False),
    )

    beruehrt = [p for p, _ in o2.termine if p == ALT_ID]
    beruehrt += [c for c, _, _ in o2.entwuerfe if ALT_ID in str(c)]
    pruefe(
        "14",
        "der genannte Alt-Entwurf wird NICHT angefasst -- weder geplant noch geaendert",
        not beruehrt
        and o2.termine == [("cmtATTRAPPE0001", "2026-09-02T10:00:00+02:00")]
        and len(o2.entwuerfe) == 1,
        f"Termine {o2.termine}, {len(o2.entwuerfe)} Entwurf/Entwuerfe, Beruehrungen {len(beruehrt)}",
    )

    print(f"\n[pruef] {bestanden} von {GESAMT} bestanden.")
    if funde:
        print("[pruef] Funde:")
        for f in funde:
            print(f"[pruef]   - {f}")
    return 0 if not funde else 1


if __name__ == "__main__":
    sys.exit(main())

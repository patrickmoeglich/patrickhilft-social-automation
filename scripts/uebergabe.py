"""Uebergabe eines FERTIGEN Beitrags aus KZ-Privat an die Telegram-Freigabe (Phase 7A).

Was dieses Skript ist -- und was es ausdruecklich nicht ist:

    main.py       erzeugt einen Beitrag   und laesst ihn freigeben.
    uebergabe.py  bekommt einen fertigen  und laesst ihn freigeben.

**Es wird hier nichts erzeugt.** Weder `generate_post` noch `image_gen` werden
importiert, und das ist kein Zufall, sondern der Kern der Aufteilung: KZ-Privat
ist Eigentuemer des Inhalts, diese Pipeline ist der Zustellweg. Wuerde hier auch
nur ersatzweise generiert, gaebe es zwei Wahrheiten ueber denselben Beitrag --
genau das, was die Aufteilung verhindern soll.

**Die Profil-IDs kommen ausschliesslich aus Secrets.** Uebergeben werden nur
logische Plattformnamen ("facebook", "linkedin"); die Zuordnung zur Ocoya-ID
passiert hier, aus `OCOYA_PROFIL_<PLATTFORM>`. **Kein Wert wird je ausgegeben** --
weder im Protokoll noch in einer Telegram-Nachricht noch im Ergebnisartefakt.
Workflow-Inputs stehen im Klartext im Run-Protokoll; deshalb duerfen dort keine
IDs stehen.

**Alles Netz steckt in `bot` und `ocoya`.** Beide werden hereingereicht, nicht
hier gebaut -- so laesst sich der ganze Ablauf ohne Netz und ohne einen Cent
pruefen (`test_uebergabe.py`).
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# Bewusst NICHT importiert: generate_post, image_gen. Siehe Modulkopf.
from telegram_bot import TelegramBot, approval_keyboard
from ocoya_client import OcoyaClient

ERGEBNIS_DATEI = "uebergabe-ergebnis.json"

#: Die Plattformnamen, die KZ-Privat kennt (`BeitragPlattform` in types.ts).
ERLAUBTE_PLATTFORMEN = ["instagram", "tiktok", "linkedin", "x", "facebook"]


@dataclass
class Eingaben:
    kz_beitrag_id: str
    caption: str
    hashtags: List[str]
    bild_url: str
    plattformen: List[str]
    scheduled_at: str
    #: Optional: Die postGroupId eines aelteren Ocoya-Entwurfs, den dieser
    #: Beitrag inhaltlich ersetzt.
    #:
    #: **Reine Dokumentation.** Dieses Skript fasst den genannten Entwurf nicht
    #: an -- kein Loeschen, kein Einplanen, kein Aendern. Er steht im Artefakt,
    #: damit KZ-Privat spaeter zuordnen kann, welcher alte Entwurf zu welchem
    #: neuen gehoert; **was mit ihm geschieht, entscheidet Patrick.**
    ersetzt_ocoya_gruppe_id: str = ""


@dataclass
class Ergebnis:
    kz_beitrag_id: str
    entscheidung: str
    ocoya_post_group_id: Optional[str] = None
    termin: Optional[str] = None
    hinweis: str = ""
    plattformen: List[str] = field(default_factory=list)
    #: Nur Zuordnung. Dieser Lauf hat den genannten Entwurf nicht angefasst.
    ersetzt_ocoya_gruppe_id: str = ""

    def als_dict(self) -> dict:
        return {
            "kz_beitrag_id": self.kz_beitrag_id,
            "entscheidung": self.entscheidung,
            "ocoya_post_group_id": self.ocoya_post_group_id,
            "termin": self.termin,
            "hinweis": self.hinweis,
            # Namen, keine IDs -- das Artefakt ist so wenig geheim wie moeglich.
            "plattformen": self.plattformen,
            "ersetzt_ocoya_gruppe_id": self.ersetzt_ocoya_gruppe_id,
        }


class EingabeFehler(ValueError):
    """Eine Eingabe taugt nicht. Es wird nichts gesendet und nichts angelegt."""


def _pflicht(werte: dict, name: str) -> str:
    wert = (werte.get(name) or "").strip()
    if not wert:
        raise EingabeFehler(f"{name} fehlt oder ist leer.")
    return wert


def eingaben_lesen(umgebung: dict) -> Eingaben:
    """Die Eingaben aus der Umgebung holen und streng pruefen.

    **Gelesen wird aus der Umgebung und nicht von der Kommandozeile:** Argumente
    stehen in Prozesslisten, Umgebungsvariablen nicht. Geheim ist hier zwar
    nichts -- aber die Gewohnheit gehoert an die Stelle, an der spaeter etwas
    Geheimes stehen koennte.
    """
    kz_id = _pflicht(umgebung, "KZ_BEITRAG_ID")
    if not re.fullmatch(r"\d+", kz_id):
        raise EingabeFehler(f"KZ_BEITRAG_ID muss eine Zahl sein, war: {kz_id!r}")

    caption = _pflicht(umgebung, "CAPTION")

    bild_url = _pflicht(umgebung, "BILD_URL")
    if not bild_url.startswith("https://"):
        raise EingabeFehler("BILD_URL muss eine https-Adresse sein.")

    scheduled_at = _pflicht(umgebung, "SCHEDULED_AT")
    try:
        wann = datetime.fromisoformat(scheduled_at)
    except ValueError as exc:
        raise EingabeFehler(f"SCHEDULED_AT ist kein ISO-8601-Zeitpunkt: {exc}") from exc
    if wann.tzinfo is None:
        # Ohne Versatz waere unklar, ob 10:00 Berliner Zeit oder UTC gemeint ist.
        # Genau diese Zweideutigkeit hat KZ-Privat mit D3 einmal geklaert; sie
        # wird hier nicht wieder eingefuehrt.
        raise EingabeFehler("SCHEDULED_AT braucht einen Zeitzonen-Versatz, z. B. +02:00.")

    roh_plattformen = _pflicht(umgebung, "PLATTFORMEN")
    plattformen = [p.strip().lower() for p in roh_plattformen.split(",") if p.strip()]
    if not plattformen:
        raise EingabeFehler("PLATTFORMEN ist leer.")
    unbekannt = [p for p in plattformen if p not in ERLAUBTE_PLATTFORMEN]
    if unbekannt:
        raise EingabeFehler(
            f"Unbekannte Plattform(en): {', '.join(unbekannt)}. "
            f"Erlaubt: {', '.join(ERLAUBTE_PLATTFORMEN)}"
        )

    ersetzt = (umgebung.get("ERSETZT_OCOYA_GRUPPE_ID") or "").strip()
    if ersetzt and not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", ersetzt):
        raise EingabeFehler(
            "ERSETZT_OCOYA_GRUPPE_ID sieht nicht wie eine Ocoya-Id aus."
        )

    roh_tags = (umgebung.get("HASHTAGS") or "").strip()
    hashtags = [t.strip().lstrip("#") for t in roh_tags.replace(",", " ").split() if t.strip()]

    return Eingaben(
        kz_beitrag_id=kz_id,
        caption=caption,
        hashtags=hashtags,
        bild_url=bild_url,
        plattformen=plattformen,
        scheduled_at=scheduled_at,
        ersetzt_ocoya_gruppe_id=ersetzt,
    )


def profile_aufloesen(plattformen: List[str], umgebung: dict) -> List[str]:
    """Logische Plattformnamen -> Ocoya-Profil-IDs, ausschliesslich aus Secrets.

    **Gibt nie eine ID aus -- auch nicht in der Fehlermeldung.** Fehlt ein
    Secret, wird der Plattformname genannt und sonst nichts; das reicht zum
    Beheben und verraet nichts.
    """
    ids: List[str] = []
    fehlend: List[str] = []
    for p in plattformen:
        wert = (umgebung.get(f"OCOYA_PROFIL_{p.upper()}") or "").strip()
        if not wert:
            fehlend.append(p)
            continue
        ids.append(wert)
    if fehlend:
        raise EingabeFehler(
            "Fuer diese Plattform(en) ist kein Profil-Secret hinterlegt: "
            + ", ".join(fehlend)
            + f". Erwartet wird je ein Secret OCOYA_PROFIL_{fehlend[0].upper()}."
        )
    return ids


def caption_mit_tags(eingaben: Eingaben) -> str:
    """Derselbe Aufbau wie in `main.py` -- Text, Leerzeile, Hashtags."""
    if not eingaben.hashtags:
        return eingaben.caption
    return eingaben.caption + "\n\n" + " ".join(f"#{t}" for t in eingaben.hashtags)


def nachricht_bauen(eingaben: Eingaben) -> str:
    """Die Telegram-Nachricht -- **mit sichtbarer KZ-Beitrags-ID.**

    Die Id steht oben und nicht im Kleingedruckten: Patrick entscheidet am Handy
    und muss ohne Nachschlagen wissen, worueber. Sie ist zugleich die Klammer,
    an der die Rueckmeldung haengt.
    """
    kopf = f"<b>Freigabe: KZ-Beitrag {html.escape(eingaben.kz_beitrag_id)}</b>"
    plattformen = ", ".join(eingaben.plattformen)
    tags = " ".join(f"#{t}" for t in eingaben.hashtags)
    zeilen = [
        kopf,
        f"<i>Kanäle: {html.escape(plattformen)} · geplant: {html.escape(eingaben.scheduled_at)}</i>",
        "",
        html.escape(eingaben.caption),
    ]
    if tags:
        zeilen += ["", html.escape(tags)]
    zeilen += ["", f'<a href="{html.escape(eingaben.bild_url)}">Bild ansehen</a>']
    return "\n".join(zeilen)


def uebergeben(bot, ocoya, eingaben: Eingaben, profil_ids: List[str], warte_sekunden: int) -> Ergebnis:
    """Der ganze Ablauf, ohne selbst Netz aufzubauen.

    **Reihenfolge ist die Sicherung:** erst fragen, dann anlegen. Bei Ablehnung
    oder Zeitlimit entsteht bei Ocoya nichts -- kein Entwurf, der spaeter
    aufgeraeumt werden muesste.

    **Die Tastatur kommt ohne "Neu generieren"** -- `allow_regenerate=False`.
    Der Knopf haette hier keine Bedeutung: Es gibt nichts zu generieren, der Text
    gehoert KZ-Privat. **Ihn wegzulassen ist besser, als ihn zu erklaeren** --
    ein Knopf, der auf einen Hinweistext fuehrt, ist ein Fehler im Dialog und
    nicht in der Bedienung.

    **Eine einzige Frage, keine Schleife.** Mit der abgeschalteten Taste kann von
    dieser Nachricht nur `approve` oder `cancel` kommen; alles andere waere ein
    Ausreisser und gilt als Ablehnung. Fremde Rueckmeldungen aelterer Nachrichten
    filtert `telegram_bot._wait()` seit `d1f05e0` selbst heraus und bestaetigt
    sie -- der Update-Offset lebt jetzt an der Bot-Instanz und nicht mehr je
    Aufruf. **Ohne diese Aenderung haette eine Schleife hier alte Knopfdruecke
    endlos wiedergekaut.**
    """
    ergebnis = Ergebnis(
        kz_beitrag_id=eingaben.kz_beitrag_id,
        entscheidung="offen",
        plattformen=list(eingaben.plattformen),
        ersetzt_ocoya_gruppe_id=eingaben.ersetzt_ocoya_gruppe_id,
    )

    message_id = bot.send_message(
        nachricht_bauen(eingaben), reply_markup=approval_keyboard(allow_regenerate=False)
    )

    entscheidung = bot.wait_for_decision(message_id, timeout_seconds=warte_sekunden)

    if entscheidung is None:
        bot.send_message(
            f"⏱️ <b>Zeitlimit</b> — KZ-Beitrag {eingaben.kz_beitrag_id} wurde nicht "
            "freigegeben. Es wurde nichts eingeplant."
        )
        ergebnis.entscheidung = "zeitlimit"
        return ergebnis

    if entscheidung != "approve":
        bot.send_message(
            f"❌ <b>Abgelehnt</b> — KZ-Beitrag {eingaben.kz_beitrag_id}. "
            "Es wurde nichts eingeplant."
        )
        ergebnis.entscheidung = "abgelehnt"
        if entscheidung != "cancel":
            # Sollte mit abgeschalteter Taste nicht vorkommen. Festgehalten statt
            # verschwiegen: Wer den Fall spaeter sieht, soll wissen, was ankam.
            ergebnis.hinweis = f"unerwartete Rueckmeldung: {entscheidung}"
        return ergebnis

    entwurf = ocoya.create_draft_post(caption_mit_tags(eingaben), profil_ids, [eingaben.bild_url])
    post_id = entwurf.get("postGroupId") or entwurf.get("id") or entwurf.get("_id")
    if not post_id:
        raise RuntimeError("Ocoya-Antwort enthielt keine Post-ID.")
    ocoya.schedule_post(post_id, eingaben.scheduled_at)

    bot.send_message(
        f"✅ <b>Eingeplant</b> — KZ-Beitrag {eingaben.kz_beitrag_id} für "
        f"{html.escape(eingaben.scheduled_at)}."
    )
    ergebnis.entscheidung = "freigegeben"
    ergebnis.ocoya_post_group_id = str(post_id)
    ergebnis.termin = eingaben.scheduled_at
    return ergebnis


def ergebnis_schreiben(ergebnis: Ergebnis, pfad: str = ERGEBNIS_DATEI) -> None:
    with open(pfad, "w", encoding="utf-8") as datei:
        json.dump(ergebnis.als_dict(), datei, ensure_ascii=False, indent=2)


def main() -> int:
    try:
        eingaben = eingaben_lesen(os.environ)
        profil_ids = profile_aufloesen(eingaben.plattformen, os.environ)
    except EingabeFehler as fehler:
        print(f"Eingabe unbrauchbar: {fehler}", file=sys.stderr)
        return 1

    # Nur die Anzahl, nie die Werte.
    print(
        f"Uebergabe KZ-Beitrag {eingaben.kz_beitrag_id}: "
        f"{len(profil_ids)} Profil(e) fuer {', '.join(eingaben.plattformen)}, "
        f"geplant fuer {eingaben.scheduled_at}"
    )

    warte_minuten = int(os.environ.get("POLL_TIMEOUT_MINUTES", "60"))
    ergebnis = uebergeben(TelegramBot(), OcoyaClient(), eingaben, profil_ids, warte_minuten * 60)
    ergebnis_schreiben(ergebnis)
    print(f"Entscheidung: {ergebnis.entscheidung}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

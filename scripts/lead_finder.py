"""Findet und priorisiert lokale Unternehmen mit schwacher Online-Praesenz als Leads fuer
ein eigenes Website-/Social-Media-Angebot und pflegt sie in eine persistente Master-Liste
(leads/leads.csv) ein.

Dieses Skript recherchiert nur: Es liest eine von dir gepflegte Liste oeffentlich bekannter
Unternehmen (siehe leads/prospects.example.csv), prueft deren oeffentliche Website (kein Login,
kein Scraping von Instagram/Facebook selbst) inkl. Impressum/Kontakt, schaetzt eine Prioritaet
und traegt Befund + Telefonnummer in die Master-Liste ein.

Es verschickt nichts. Die Ansprache erfolgt telefonisch (siehe scripts/lead_caller.py) - kalte
Werbe-Mails brauchen im B2B eine vorherige Einwilligung (§ 7 Abs. 2 UWG), das Telefon ist bei
sachlichem Bezug ueber die mutmassliche Einwilligung zulaessig. Verantwortung dafuer liegt bei dir.

Der Gespraechsleitfaden (generate_call_guide) wird bewusst nicht hier, sondern erst beim Anruf-
Modul erzeugt - so kostet er nur fuer die tatsaechlich angerufenen Leads einen API-Call.

Nutzung:
    python scripts/lead_finder.py leads/prospects.csv
    python scripts/lead_finder.py leads/prospects.csv --store leads/leads.csv
"""
import argparse
import csv
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

import lead_store

REPO_ROOT = Path(__file__).resolve().parent.parent
VOICE_PROFILE_FILE = REPO_ROOT / "prompts" / "voice_profile_b2b.md"
DEFAULT_STORE = REPO_ROOT / "leads" / "leads.csv"
MODEL = "claude-opus-4-8"
REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; LeadResearchBot/1.0; manuelle Vertriebsrecherche)"

# Rate-Limiting: Mindestabstand zwischen HTTP-Requests, damit wir fremde Server hoeflich
# und nicht in Bursts belasten (gilt global ueber alle Prospects/Unterseiten hinweg).
REQUEST_DELAY = 1.5
# Unterseiten-Check: zusaetzlich zur Startseite werden bis zu MAX_SUBPAGES interne Seiten
# geprueft, deren URL auf typische Kontakt-/Aktivitaets-Bereiche hindeutet (Social-Links,
# Blog-Daten und Telefonnummern stehen oft im Impressum/Kontakt, nicht auf der Startseite).
MAX_SUBPAGES = 5
SUBPAGE_HINTS = (
    "impressum", "kontakt", "contact", "blog", "news", "aktuelles",
    "neuigkeiten", "presse", "ueber-uns", "about", "team",
)

SOCIAL_PATTERNS = {
    "instagram": re.compile(r"instagram\.com/[A-Za-z0-9_.\-/]+", re.IGNORECASE),
    "facebook": re.compile(r"facebook\.com/[A-Za-z0-9_.\-/]+", re.IGNORECASE),
    "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[A-Za-z0-9_\-/]+", re.IGNORECASE),
}
TARGET_PLATFORMS = list(SOCIAL_PATTERNS.keys())

MONTH_NUMBERS = {
    "januar": 1, "january": 1, "februar": 2, "february": 2, "märz": 3, "march": 3,
    "april": 4, "mai": 5, "may": 5, "juni": 6, "june": 6, "juli": 7, "july": 7,
    "august": 8, "september": 9, "oktober": 10, "october": 10,
    "november": 11, "dezember": 12, "december": 12,
}
DATE_PATTERN = re.compile(rf"({'|'.join(MONTH_NUMBERS)})\s+(\d{{4}})", re.IGNORECASE)
STALE_MONTHS_THRESHOLD = 6

# Telefon-Extraktion (Heuristik). tel:-Links sind am zuverlaessigsten; Textmuster nur in der
# Naehe eines Telefon-Labels, damit nicht jede lange Zahl (PLZ, Steuernummer) getroffen wird.
TEL_LINK_PATTERN = re.compile(r"tel:(\+?[0-9()\-\s/\.]{6,})", re.IGNORECASE)
PHONE_LABEL_PATTERN = re.compile(r"(?:tel\.?|telefon|fon|ruf(?:nummer)?)\b[^0-9+]{0,15}", re.IGNORECASE)
PHONE_NUMBER_PATTERN = re.compile(r"(?:\+49|0)[0-9()\-\s/\.]{5,18}\d")


@dataclass
class Prospect:
    name: str
    website: str
    industry: str = ""
    region: str = ""
    contact_name: str = ""
    phone: str = ""  # manueller Override; leer -> aus der Website geschaetzt
    notes: str = ""


@dataclass
class Analysis:
    found_platforms: List[str] = field(default_factory=list)
    latest_mentioned_date: Optional[str] = None
    months_since_update: Optional[int] = None
    phone: Optional[str] = None
    reasoning: List[str] = field(default_factory=list)
    score: int = 0


def load_prospects(csv_path: Path) -> List[Prospect]:
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            Prospect(
                name=row.get("name", "").strip(),
                website=row.get("website", "").strip(),
                industry=row.get("industry", "").strip(),
                region=row.get("region", "").strip(),
                contact_name=row.get("contact_name", "").strip(),
                phone=row.get("phone", "").strip(),
                notes=row.get("notes", "").strip(),
            )
            for row in reader
            if row.get("name", "").strip()
        ]


_last_request_time = 0.0


def _throttle() -> None:
    """Sorgt fuer mindestens REQUEST_DELAY Sekunden Abstand zwischen zwei HTTP-Requests."""
    global _last_request_time
    wait = REQUEST_DELAY - (time.monotonic() - _last_request_time)
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.monotonic()


def _normalize_url(url: str) -> Optional[str]:
    if not url:
        return None
    if not url.startswith("http"):
        url = "https://" + url
    return url


def _fetch(url: str) -> Optional[str]:
    """Laedt eine bereits normalisierte URL, mit globalem Rate-Limiting."""
    if not url:
        return None
    _throttle()
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return None


def _same_host(base_url: str, candidate_url: str) -> bool:
    base = urlparse(base_url).netloc.lower().removeprefix("www.")
    cand = urlparse(candidate_url).netloc.lower().removeprefix("www.")
    return bool(cand) and cand == base


def _internal_subpage_urls(base_url: str, html_text: str, limit: int) -> List[str]:
    """Findet bis zu `limit` interne Links, deren URL auf Kontakt-/Aktivitaets-Seiten hindeutet."""
    found: List[str] = []
    seen = {base_url.rstrip("/")}
    for href in re.findall(r"""href=["']([^"'#]+)["']""", html_text, re.IGNORECASE):
        absolute = urljoin(base_url, href.strip())
        if not absolute.startswith("http") or not _same_host(base_url, absolute):
            continue
        if not any(hint in absolute.lower() for hint in SUBPAGE_HINTS):
            continue
        key = absolute.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        found.append(absolute)
        if len(found) >= limit:
            break
    return found


def gather_site_text(website: str) -> Tuple[Optional[str], int]:
    """Laedt Startseite + relevante Unterseiten und gibt (kombinierter Text, Anzahl geladener Seiten) zurueck."""
    base = _normalize_url(website)
    if base is None:
        return None, 0
    home = _fetch(base)
    if home is None:
        return None, 0
    pages = [home]
    for sub in _internal_subpage_urls(base, home, MAX_SUBPAGES):
        text = _fetch(sub)
        if text:
            pages.append(text)
    return "\n".join(pages), len(pages)


def _clean_phone(raw: str) -> Optional[str]:
    cleaned = re.sub(r"[^\d+]", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    digits = re.sub(r"\D", "", cleaned)
    if not 6 <= len(digits) <= 15:
        return None
    return cleaned


def extract_phone(html_text: str) -> Optional[str]:
    """Schaetzt die Telefonnummer aus dem Seitentext (Heuristik, manuell verifizieren).

    Reihenfolge: 1) tel:-Link (zuverlaessig), 2) Zahl direkt hinter einem Telefon-Label.
    """
    link = TEL_LINK_PATTERN.search(html_text)
    if link:
        phone = _clean_phone(link.group(1))
        if phone:
            return phone
    for label in PHONE_LABEL_PATTERN.finditer(html_text):
        snippet = html_text[label.end():label.end() + 30]
        number = PHONE_NUMBER_PATTERN.search(snippet)
        if number:
            phone = _clean_phone(number.group(0))
            if phone:
                return phone
    return None


def _months_since(year: int, month: int) -> int:
    now = datetime.now()
    return (now.year - year) * 12 + (now.month - month)


def analyze_website(website: str) -> Analysis:
    analysis = Analysis()
    html_text, pages_checked = gather_site_text(website)
    if html_text is None:
        analysis.reasoning.append("Website nicht erreichbar oder keine URL angegeben - manuell pruefen")
        return analysis

    page_note = "Startseite" if pages_checked <= 1 else f"Startseite + {pages_checked - 1} Unterseite(n)"
    analysis.phone = extract_phone(html_text)

    analysis.found_platforms = [p for p, pattern in SOCIAL_PATTERNS.items() if pattern.search(html_text)]
    missing = [p for p in TARGET_PLATFORMS if p not in analysis.found_platforms]

    if not analysis.found_platforms:
        analysis.score += 3
        analysis.reasoning.append(f"Keine Social-Media-Links gefunden ({page_note} geprueft)")
    elif missing:
        analysis.score += len(missing)
        analysis.reasoning.append(
            f"Verlinkt: {', '.join(analysis.found_platforms)} - fehlt: {', '.join(missing)} ({page_note} geprueft)"
        )
    else:
        analysis.reasoning.append("Alle Ziel-Plattformen (Instagram/Facebook/LinkedIn) verlinkt")

    raw_dates = [(int(year), MONTH_NUMBERS[month.lower()]) for month, year in DATE_PATTERN.findall(html_text)]
    # Nur Daten in Vergangenheit/aktuellem Monat als "Aktivitaet" werten. Zukunftsdaten (Event-
    # Ankuendigungen etc.) wuerden months_since negativ machen und die Stale-Heuristik aushebeln.
    past_dates = [(y, m) for (y, m) in raw_dates if _months_since(y, m) >= 0]
    if past_dates:
        year, month = max(past_dates)
        analysis.latest_mentioned_date = f"{month:02d}/{year}"
        analysis.months_since_update = _months_since(year, month)
        if analysis.months_since_update >= STALE_MONTHS_THRESHOLD:
            analysis.score += 2
            analysis.reasoning.append(
                f"Neuestes gefundenes Datum: {analysis.latest_mentioned_date} "
                f"(~{analysis.months_since_update} Monate her, Heuristik - manuell verifizieren; "
                "Copyright-/Footer-Jahre koennen taeuschen)"
            )
    elif raw_dates:
        analysis.reasoning.append(
            "Nur Datumsangaben in der Zukunft gefunden (vermutlich Termine/Events) - fuer Aktualitaet ignoriert"
        )
    else:
        analysis.reasoning.append("Kein Datum/Blog-Bereich gefunden - Aktivitaet nicht automatisch einschaetzbar")

    return analysis


def load_voice_profile() -> str:
    return VOICE_PROFILE_FILE.read_text(encoding="utf-8")


def generate_call_guide(*, name: str, industry: str, region: str, contact_name: str,
                        befund: str, voice_profile: str) -> str:
    """Erzeugt den vierteiligen Gespraechsleitfaden (Aufhaenger / Folge / 2 Rueckfragen / Einwand).

    Das Voice-Profil wird als `system` uebergeben (nicht in den User-Prompt gemischt), damit es
    sich ohne Codeaenderung anpassen laesst. Der User-Prompt enthaelt nur die Lead-Daten.
    """
    import anthropic  # lokaler Import: die Recherche selbst braucht keinen Anthropic-Key

    client = anthropic.Anthropic()
    user_prompt = (
        f"Firma: {name}\n"
        f"Branche: {industry or 'unbekannt'}\n"
        f"Ort: {region or 'unbekannt'}\n"
        f"Ansprechpartner: {contact_name or 'unbekannt'}\n\n"
        f"Befunde aus der automatischen Website-Pruefung (Heuristik, ggf. ungenau):\n{befund}"
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=voice_profile,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return next(block.text for block in response.content if block.type == "text").strip()


def run(csv_path: Path, store_path: Path) -> None:
    prospects = load_prospects(csv_path)
    if not prospects:
        print(f"Keine Prospects in {csv_path} gefunden.")
        return

    rows = lead_store.load(store_path)
    neu = aktualisiert = ohne_telefon = 0

    for prospect in prospects:
        print(f"Analysiere {prospect.name} ({prospect.website}) ...")
        analysis = analyze_website(prospect.website)
        phone = prospect.phone or (analysis.phone or "")
        if not phone:
            ohne_telefon += 1
            analysis.reasoning.append("Keine Telefonnummer gefunden - fuer die Anrufliste manuell ergaenzen")
        outcome = lead_store.upsert_research(
            rows,
            name=prospect.name, website=prospect.website, industry=prospect.industry,
            region=prospect.region, contact_name=prospect.contact_name, phone=phone,
            score=analysis.score, befund=" | ".join(analysis.reasoning),
        )
        neu += outcome == "neu"
        aktualisiert += outcome == "aktualisiert"

    lead_store.save(store_path, rows)

    print(f"\n{len(prospects)} Prospects verarbeitet ({neu} neu, {aktualisiert} aktualisiert). "
          f"Master-Liste: {store_path}")
    if ohne_telefon:
        print(f"  Achtung: {ohne_telefon} ohne Telefonnummer - Anruf erst nach manueller Ergaenzung moeglich.")
    top = lead_store.selectable(rows, lead_store.today(), limit=5)
    print(f"Naechste bis zu 5 anrufbare Leads (hoechster Score = schwaechste Praesenz = hoechste Prioritaet):")
    for row in top:
        tel = row["phone"] or "KEINE NUMMER"
        print(f"  - {row['name']} (Score {row['score']}, {tel}): {row['befund']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "csv_path", type=Path,
        help="CSV mit Prospects (Spalten: name,website,industry,region,contact_name,phone,notes)",
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE,
                        help=f"Pfad der persistenten Master-Liste (Default: {DEFAULT_STORE})")
    args = parser.parse_args()

    run(args.csv_path, args.store)
    return 0


if __name__ == "__main__":
    sys.exit(main())

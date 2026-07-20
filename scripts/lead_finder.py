"""Findet und priorisiert lokale Unternehmen mit schwacher Social-Media-Praesenz als
Leads fuer ein eigenes Social-Media-Management-Angebot, und entwirft dazu passende
Outreach-Texte per Anthropic API.

Wichtig: Dieses Skript verschickt nichts automatisch. Es liest eine von dir gepflegte
Liste oeffentlich bekannter Unternehmen (siehe leads/prospects.example.csv), prueft nur
deren oeffentliche Website (kein Login, kein Scraping von Instagram/Facebook selbst),
und schreibt priorisierte Leads + Entwurfstexte in eine CSV. Versand bleibt manuell und
liegt in deiner Verantwortung (DSGVO/Wettbewerbsrecht bei B2B-Kaltakquise beachten).

Nutzung:
    python scripts/lead_finder.py leads/prospects.csv
    python scripts/lead_finder.py leads/prospects.csv --top 5 --no-draft
"""
import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import anthropic
import requests

OFFER_FILE = Path(__file__).resolve().parent.parent / "config" / "leadgen_offer.md"
MODEL = "claude-opus-4-8"
REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; LeadResearchBot/1.0; manuelle Vertriebsrecherche)"

# Rate-Limiting: Mindestabstand zwischen HTTP-Requests, damit wir fremde Server hoeflich
# und nicht in Bursts belasten (gilt global ueber alle Prospects/Unterseiten hinweg).
REQUEST_DELAY = 1.5
# Unterseiten-Check: zusaetzlich zur Startseite werden bis zu MAX_SUBPAGES interne Seiten
# geprueft, deren URL auf typische Kontakt-/Aktivitaets-Bereiche hindeutet (Social-Links und
# Blog-Daten stehen oft nicht auf der Startseite, sondern im Footer/Impressum bzw. unter /blog).
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


@dataclass
class Prospect:
    name: str
    website: str
    industry: str = ""
    region: str = ""
    contact_name: str = ""
    contact_email: str = ""
    notes: str = ""


@dataclass
class Analysis:
    found_platforms: List[str] = field(default_factory=list)
    latest_mentioned_date: Optional[str] = None
    months_since_update: Optional[int] = None
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
                contact_email=row.get("contact_email", "").strip(),
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


def generate_outreach(prospect: Prospect, analysis: Analysis, offer_brief: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    reasoning_text = "\n".join(f"- {r}" for r in analysis.reasoning)
    prompt = (
        "Schreibe eine kurze, persoenliche Erstkontakt-Nachricht (E-Mail, max. 120 Woerter, "
        "Deutsch, ohne Betreffzeile) an folgendes Unternehmen, basierend auf diesem "
        f"Angebots-Briefing:\n\n{offer_brief}\n\n"
        f"Unternehmen: {prospect.name}\n"
        f"Branche: {prospect.industry or 'unbekannt'}\n"
        f"Region: {prospect.region or 'unbekannt'}\n"
        f"Ansprechpartner: {prospect.contact_name or 'unbekannt - allgemein formulieren'}\n\n"
        "Beobachtete Anhaltspunkte zur Social-Media-Praesenz (Heuristik, ggf. ungenau - "
        f"vorsichtig andeuten, nicht als Fakt behaupten):\n{reasoning_text}\n\n"
        "Ton: freundlich, konkret, ohne Floskeln, mit einer klaren, niedrigschwelligen "
        "Handlungsaufforderung laut Briefing. Keine falschen Behauptungen ueber das "
        "Unternehmen aufstellen."
    )
    response = client.messages.create(model=MODEL, max_tokens=500, messages=[{"role": "user", "content": prompt}])
    return next(block.text for block in response.content if block.type == "text").strip()


def run(csv_path: Path, top_n: int, draft: bool, output_path: Path) -> None:
    prospects = load_prospects(csv_path)
    if not prospects:
        print(f"Keine Prospects in {csv_path} gefunden.")
        return

    offer_brief = OFFER_FILE.read_text(encoding="utf-8") if draft else ""

    results = []
    for prospect in prospects:
        print(f"Analysiere {prospect.name} ({prospect.website}) ...")
        results.append((prospect, analyze_website(prospect.website)))

    results.sort(key=lambda pair: pair[1].score, reverse=True)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "website", "score", "reasoning", "outreach_draft"])
        for i, (prospect, analysis) in enumerate(results):
            outreach = ""
            if draft and i < top_n:
                try:
                    outreach = generate_outreach(prospect, analysis, offer_brief)
                except Exception as exc:
                    outreach = f"[Fehler bei Entwurf: {exc}]"
            writer.writerow([prospect.name, prospect.website, analysis.score, " | ".join(analysis.reasoning), outreach])

    print(f"\n{len(results)} Leads analysiert. Ergebnis geschrieben nach: {output_path}")
    print(f"Top {min(top_n, len(results))} Leads (hoechster Score = schwaechste Praesenz = hoechste Prioritaet):")
    for prospect, analysis in results[:top_n]:
        print(f"  - {prospect.name} (Score {analysis.score}): {'; '.join(analysis.reasoning)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "csv_path", type=Path,
        help="CSV mit Prospects (Spalten: name,website,industry,region,contact_name,contact_email,notes)",
    )
    parser.add_argument("--top", type=int, default=10, help="Anzahl Leads mit Outreach-Entwurf (Default: 10)")
    parser.add_argument(
        "--no-draft", action="store_true",
        help="Nur analysieren/scoren, keine Outreach-Texte generieren (kein Anthropic-API-Call noetig)",
    )
    parser.add_argument("--output", type=Path, default=None, help="Pfad fuer die Ergebnis-CSV")
    args = parser.parse_args()

    output_path = args.output or Path("leads") / f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run(args.csv_path, args.top, draft=not args.no_draft, output_path=output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

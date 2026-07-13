"""Analysiert eine Webseite und erstellt eine professionell optimierte Neuversion.

Was das Skript macht:
  1. Laedt die Webseite herunter und misst Technik-Werte (Geschwindigkeit, Groesse,
     Mobil-Tauglichkeit, SEO-Basics, Bilder, Skripte).
  2. Laesst Claude das Design wie ein Profi-Webdesigner bewerten und schreibt einen
     verstaendlichen Bericht auf Deutsch (bericht.md).
  3. Baut aus den echten Inhalten der Seite eine komplett neu designte, moderne,
     mobile-optimierte Version als fertige HTML-Datei (neue-webseite.html).

Wichtig: Das Skript kann eine fremde Live-Webseite nicht direkt veraendern (dafuer
braeuchte man Zugriff auf deren Server). Die erzeugte HTML-Datei kann man aber
hochladen, als Vorschau an Kunden schicken oder als Vorlage fuer den Umbau nutzen.

Nutzung:
    python scripts/website_optimizer.py https://beispiel-firma.de
    python scripts/website_optimizer.py https://beispiel-firma.de --nur-analyse
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import anthropic
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

MODEL = "claude-opus-4-8"
REQUEST_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "website_optimierung"

# Wie viel Roh-HTML/CSS maximal an Claude geschickt wird (Zeichen)
MAX_HTML_CHARS = 80_000
MAX_CSS_CHARS = 20_000


def _load_dotenv() -> None:
    """Laedt Variablen aus der .env im Projektordner, falls vorhanden (kein Overwrite)."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Schritt 1: Webseite laden und technisch analysieren
# ---------------------------------------------------------------------------

def fetch_page(url: str) -> tuple[requests.Response, float]:
    start = time.monotonic()
    resp = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate, br"},
        allow_redirects=True,
    )
    elapsed = time.monotonic() - start
    resp.raise_for_status()
    return resp, elapsed


def fetch_css_snippets(soup: BeautifulSoup, base_url: str) -> str:
    """Laedt die ersten verlinkten Stylesheets (gekuerzt) als Design-Kontext."""
    snippets: list[str] = []
    total = 0
    for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = link.get("href")
        if not href or total >= MAX_CSS_CHARS:
            continue
        css_url = urljoin(base_url, href)
        try:
            r = requests.get(css_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
            if r.ok and "text" in r.headers.get("content-type", "css"):
                chunk = r.text[: MAX_CSS_CHARS - total]
                snippets.append(f"/* --- {css_url} --- */\n{chunk}")
                total += len(chunk)
        except requests.RequestException:
            continue
    return "\n\n".join(snippets)


def head_size(url: str) -> int | None:
    """Fragt die Dateigroesse eines Bildes per HEAD-Request ab (Bytes)."""
    try:
        r = requests.head(url, timeout=8, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
        length = r.headers.get("content-length")
        return int(length) if length else None
    except (requests.RequestException, ValueError):
        return None


# Bilder ueber diese Groesse werden nicht geladen, um Pixelmasse zu ermitteln (Bytes)
MAX_IMAGE_DOWNLOAD_BYTES = 5_000_000


def native_image_size(url: str) -> tuple[int, int] | None:
    """Ermittelt die tatsaechliche Pixelbreite/-hoehe eines Bildes.

    Wird gebraucht, damit Claude Original-Bilder im Redesign nicht groesser
    darstellt als ihre native Aufloesung erlaubt (sonst verpixelt/unscharf).
    """
    try:
        r = requests.get(
            url, timeout=10, headers={"User-Agent": USER_AGENT},
            stream=True,
        )
        if not r.ok:
            return None
        content_length = r.headers.get("content-length")
        if content_length and int(content_length) > MAX_IMAGE_DOWNLOAD_BYTES:
            return None
        data = r.content[:MAX_IMAGE_DOWNLOAD_BYTES]
        with Image.open(BytesIO(data)) as img:
            return img.size  # (Breite, Hoehe) in Pixeln
    except Exception:
        return None


def analyze(url: str, resp: requests.Response, elapsed: float, soup: BeautifulSoup) -> dict:
    """Sammelt messbare Fakten ueber die Seite fuer den Bericht."""
    head = soup.find("head")
    parsed = urlparse(resp.url)

    # Bilder pruefen (max. 12 per HEAD-Request vermessen)
    images = soup.find_all("img")
    image_facts = []
    for img in images[:12]:
        src = img.get("src") or img.get("data-src")
        if not src or src.startswith("data:"):
            continue
        abs_src = urljoin(resp.url, src)
        image_facts.append({
            "url": abs_src,
            "alt_vorhanden": bool(img.get("alt")),
            "lazy_loading": img.get("loading") == "lazy",
            "groesse_kb": (lambda s: round(s / 1024) if s else None)(head_size(abs_src)),
        })

    scripts = soup.find_all("script", src=True)
    blocking_scripts = [
        s.get("src") for s in (head.find_all("script", src=True) if head else [])
        if not s.has_attr("defer") and not s.has_attr("async")
    ]

    title = soup.find("title")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    viewport = soup.find("meta", attrs={"name": "viewport"})

    return {
        "url": resp.url,
        "https": parsed.scheme == "https",
        "ladezeit_sekunden": round(elapsed, 2),
        "html_groesse_kb": round(len(resp.content) / 1024),
        "komprimierung": resp.headers.get("content-encoding", "keine"),
        "cache_header": resp.headers.get("cache-control", "keiner"),
        "server": resp.headers.get("server", "unbekannt"),
        "viewport_meta_vorhanden": viewport is not None,
        "viewport_inhalt": viewport.get("content") if viewport else None,
        "html_lang": (soup.find("html") or {}).get("lang"),
        "titel": title.get_text(strip=True) if title else None,
        "meta_description": meta_desc.get("content") if meta_desc else None,
        "h1_anzahl": len(soup.find_all("h1")),
        "anzahl_bilder": len(images),
        "bilder_ohne_alt": sum(1 for i in images if not i.get("alt")),
        "bilder_details": image_facts,
        "anzahl_scripts": len(scripts),
        "render_blockierende_scripts": blocking_scripts,
        "anzahl_stylesheets": len(soup.find_all("link", rel=lambda v: v and "stylesheet" in v)),
        "inline_styles_anzahl": len(soup.find_all(style=True)),
        "open_graph_vorhanden": bool(soup.find("meta", property=re.compile(r"^og:"))),
        "favicon_vorhanden": bool(soup.find("link", rel=re.compile("icon", re.I))),
    }


def extract_content(soup: BeautifulSoup, base_url: str) -> dict:
    """Extrahiert die echten Inhalte der Seite als Baumaterial fuer das Redesign."""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    nav_links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = urljoin(base_url, a["href"])
        if text and href not in seen and len(text) < 80:
            seen.add(href)
            nav_links.append({"text": text, "url": href})

    headings = [
        {"ebene": h.name, "text": h.get_text(" ", strip=True)}
        for h in soup.find_all(["h1", "h2", "h3"])
        if h.get_text(strip=True)
    ]

    image_urls = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and not src.startswith("data:"):
            image_urls.append({"url": urljoin(base_url, src), "alt": img.get("alt", "")})
    image_urls = image_urls[:20]

    # Native Pixelmasse ermitteln, damit Claude Bilder nicht ueber ihre echte
    # Aufloesung hinaus vergroessert (das verursacht sichtbare Unschaerfe).
    for entry in image_urls:
        size = native_image_size(entry["url"])
        if size:
            entry["native_breite_px"], entry["native_hoehe_px"] = size
        else:
            entry["native_breite_px"], entry["native_hoehe_px"] = None, None

    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))

    return {
        "navigation_links": nav_links[:40],
        "ueberschriften": headings[:40],
        "bilder": image_urls,
        "seitentext": text[:15_000],
    }


# ---------------------------------------------------------------------------
# Schritt 2: Claude-Analyse (Bericht) und Schritt 3: Redesign
# ---------------------------------------------------------------------------

def _stream_text(client: anthropic.Anthropic, **kwargs) -> str:
    """Streamt eine Claude-Antwort und zeigt dabei einen Fortschritt an."""
    chars = 0
    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            chars += len(text)
            print(f"\r   ... {chars} Zeichen erzeugt", end="", flush=True)
        message = stream.get_final_message()
    print()
    return "".join(block.text for block in message.content if block.type == "text")


def generate_report(client: anthropic.Anthropic, audit: dict, html_excerpt: str, css_excerpt: str) -> str:
    prompt = f"""Du bist ein erfahrener Webdesigner und Performance-Berater (Agentur-Niveau, Projekte ab 10.000 EUR).
Analysiere die folgende Webseite und schreibe einen Bericht auf Deutsch im Markdown-Format.

Der Bericht ist fuer den Inhaber der Webseite gedacht (kein Techniker!). Schreibe verstaendlich,
konkret und ehrlich. Struktur:

# Webseiten-Analyse: <Domain>
## Gesamtbewertung (Schulnote 1-6 + 2-3 Saetze Fazit)
## Design & professioneller Eindruck (Note + was gut ist, was schlecht ist, ganz konkret)
## Mobile Darstellung (Note + Befunde)
## Geschwindigkeit (Note + Befunde, beziehe dich auf die Messwerte)
## Suchmaschinen & Auffindbarkeit (Note + Befunde)
## Massnahmenplan (priorisierte Liste: zuerst was am meisten bringt, mit geschaetztem Aufwand leicht/mittel/hoch)

MESSWERTE (automatisch erhoben):
{json.dumps(audit, ensure_ascii=False, indent=2)}

HTML DER SEITE (gekuerzt):
{html_excerpt}

CSS DER SEITE (gekuerzt):
{css_excerpt if css_excerpt else "(kein externes CSS gefunden)"}"""

    return _stream_text(
        client,
        model=MODEL,
        max_tokens=16_000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    )


REDESIGN_STYLE_RULES = """
- NIEMALS generische KI-Aesthetik: keine ueberstrapazierten Fonts (Inter, Roboto, Arial,
  System-Fonts), keine lila Verlaeufe, keine austauschbaren Standard-Layouts. Waehle eine
  eigenstaendige, zur Branche passende Gestaltung mit stimmigen Farben und Typografie.
- SCHRIFT-WAHL (wichtig fuer Bildschirmscharfe): Verwende ausschliesslich klare, gut
  lesbare Schriften mit gleichmaessigen, kraeftigen, "harten" Strichstaerken ohne feine
  Verzierungen. VERBOTEN sind Schriften mit weichen, rundlichen oder ausschwingenden
  Details an Buchstaben wie kleinem "f", "a" oder "g" - das betrifft insbesondere
  "Fraunces" (auch aufrecht - die Schrift hat bei kleiner "optical size" bewusst weiche,
  rundliche Formen, die auf Bildschirmen unscharf wirken) sowie "Playfair Display" und
  aehnliche "soft"/"wonky" Display-Serifen. Nutze stattdessen Schriften mit klaren,
  geometrischen oder geradlinigen Formen. Fuer Ueberschriften empfohlen: "Space
  Grotesk", "Sora", "General Sans", "Bricolage Grotesque", "Fraunces" ist tabu; als
  Serifen-Alternative mit kraeftigen, klaren Strichen: "PT Serif", "Source Serif 4",
  "Bitter", "Zilla Slab". Fuer Fliesstext: "Work Sans", "Public Sans" oder "Karla".
  Nur aufrechte Schnitte (kein italic) in Strichstaerke 500-700 fuer Ueberschriften.
  Setze bei jeder Google-Fonts-Einbindung "font-optical-sizing: auto;" sowie
  "-webkit-font-smoothing: antialiased;" NUR in Kombination mit Strichstaerke >= 500,
  nie mit duennen Schriftschnitten (300/400) in grossen Ueberschriften.
- BILDGROESSEN (wichtig gegen Unschaerfe): Jedes Originalbild hat im Inhalts-JSON die
  Felder "native_breite_px"/"native_hoehe_px". Zeige ein Bild NIEMALS breiter als ca.
  1.3x seiner nativen Breite an - staerkeres Hochskalieren erzeugt sichtbare Unschaerfe.
  Sind die Originalbilder klein/niedrig aufgeloest (z.B. unter 400px Breite), baue sie
  als kleine Elemente ein (kompaktes Bilder-Grid, kleine Kacheln, Icon-Groesse) statt als
  grosse Hero-/Vollbreite-Bilder. Fehlen native Masse (null), behandle das Bild
  vorsichtshalber als klein.
- Mobile-first und vollstaendig responsiv (Flexbox/Grid, klappbares Menue auf Handy).
- Performance: alles in EINER Datei (Inline-CSS/-JS), Bilder mit loading="lazy",
  width/height-Attributen und sauberen alt-Texten, kein externes JavaScript-Framework.
- Barrierefreiheit: ausreichende Kontraste, Fokus-Zustaende, semantisches HTML
  (header/nav/main/section/footer), sinnvolle Ueberschriften-Hierarchie.
- SEO: <title>, meta description, Open-Graph-Tags, lang="de", genau eine H1.
"""


def generate_redesign(client: anthropic.Anthropic, audit: dict, content: dict, report: str) -> str:
    prompt = f"""Du bist ein Top-Webdesigner. Baue die folgende Webseite komplett neu — so, als haette
eine Design-Agentur 10.000 EUR dafuer bekommen. Erstelle EINE vollstaendige, eigenstaendige
HTML-Datei (mit <!DOCTYPE html>), die sofort im Browser funktioniert.

WICHTIGE REGELN:
- Verwende AUSSCHLIESSLICH die echten Inhalte unten (Texte, Ueberschriften, Kontaktdaten,
  Navigation). Erfinde KEINE Fakten, Preise, Bewertungen oder Leistungen dazu. Du darfst
  Texte kuerzen, umformulieren und besser strukturieren, aber nicht inhaltlich erfinden.
- Binde die Original-Bilder ueber ihre absoluten URLs ein, wo sie inhaltlich passen.
- Rechtliche Links (Impressum, Datenschutz) muessen erhalten bleiben und auf die
  Original-URLs zeigen.
- Antworte NUR mit dem HTML-Code, ohne Erklaerungen und ohne Markdown-Codeblock.
{REDESIGN_STYLE_RULES}

ORIGINAL-URL: {audit["url"]}

INHALTE DER ORIGINAL-SEITE:
{json.dumps(content, ensure_ascii=False, indent=2)}

DESIGN-KRITIK AUS DER ANALYSE (behebe diese Punkte):
{report[:6_000]}"""

    html = _stream_text(
        client,
        model=MODEL,
        max_tokens=64_000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    )
    # Falls das Modell doch einen Markdown-Codeblock drumherum baut: entfernen
    html = html.strip()
    if html.startswith("```"):
        html = re.sub(r"^```[a-z]*\n", "", html)
        html = re.sub(r"\n```$", "", html)
    return html


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Webseite analysieren und optimierte Neuversion erstellen")
    parser.add_argument("url", help="Adresse der Webseite, z.B. https://beispiel-firma.de")
    parser.add_argument("--nur-analyse", action="store_true", help="Nur Bericht erstellen, kein Redesign")
    args = parser.parse_args()

    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("FEHLER: ANTHROPIC_API_KEY fehlt (in .env eintragen oder als Umgebungsvariable setzen).")
        return 1

    url = args.url if args.url.startswith(("http://", "https://")) else "https://" + args.url

    print(f"1/4  Lade Webseite: {url}")
    try:
        resp, elapsed = fetch_page(url)
    except requests.RequestException as exc:
        print(f"FEHLER: Webseite konnte nicht geladen werden: {exc}")
        return 1

    soup = BeautifulSoup(resp.text, "html.parser")
    print(f"     Geladen in {elapsed:.2f}s ({round(len(resp.content) / 1024)} KB)")

    print("2/4  Analysiere Technik, Mobil-Tauglichkeit und SEO ...")
    audit = analyze(url, resp, elapsed, soup)
    css_excerpt = fetch_css_snippets(soup, resp.url)
    html_excerpt = resp.text[:MAX_HTML_CHARS]
    content = extract_content(BeautifulSoup(resp.text, "html.parser"), resp.url)

    client = anthropic.Anthropic()
    domain = urlparse(resp.url).netloc.replace("www.", "")
    out_dir = OUTPUT_ROOT / f"{domain}_{datetime.now():%Y-%m-%d_%H-%M}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("3/4  Claude bewertet Design, Geschwindigkeit und SEO (Bericht) ...")
    report = generate_report(client, audit, html_excerpt, css_excerpt)
    report_path = out_dir / "bericht.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"     Bericht gespeichert: {report_path}")

    if not args.nur_analyse:
        print("4/4  Claude baut die optimierte neue Version der Webseite ...")
        redesign = generate_redesign(client, audit, content, report)
        redesign_path = out_dir / "neue-webseite.html"
        redesign_path.write_text(redesign, encoding="utf-8")
        print(f"     Neue Webseite gespeichert: {redesign_path}")
    else:
        print("4/4  Uebersprungen (--nur-analyse)")

    print("\nFertig! Ergebnisse liegen in:")
    print(f"  {out_dir}")
    print("  - bericht.md          -> Analyse mit Noten und Massnahmenplan")
    if not args.nur_analyse:
        print("  - neue-webseite.html  -> im Browser oeffnen (Doppelklick) fuer die neue Version")
    return 0


if __name__ == "__main__":
    sys.exit(main())

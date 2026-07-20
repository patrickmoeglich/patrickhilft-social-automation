# Wöchentliche Social-Media-Automatisierung

Jeden Montag generiert Claude (Anthropic API) einen Post-Text, schickt ihn dir per
Telegram-Bot zur Freigabe, generiert danach 3 KI-Bildvorschläge (OpenAI) zur Auswahl —
oder du lädst stattdessen dein eigenes Bild hoch — und plant den fertigen Post danach
über [Ocoya](https://ocoya.com) für einen festen Zeitpunkt ein (Instagram, LinkedIn,
Facebook, X). Alles läuft in einem einzigen GitHub-Actions-Workflow — kein eigener
Server nötig.

## Wie der Ablauf funktioniert

```
GitHub Actions (Montag, 08:00 UTC oder manuell)
        │
        ▼
1. Claude generiert Thema + Caption + Hashtags     (scripts/generate_post.py)
        │
        ▼
2. Telegram-Bot schickt Text-Entwurf mit Buttons:
   ✅ Freigeben   🔄 Neu generieren   ❌ Abbrechen   (scripts/telegram_bot.py)
        │
   ┌────┴─────────────┬──────────────────┐
   ✅ Freigeben        🔄 Neu generieren   ❌ / Timeout
        │                  │                  │
        ▼                  ▼                  ▼
   weiter zu 3.       zurück zu 1.        Workflow endet,
                       (max. 4x)          nichts wird gepostet
        │
        ▼
3. Claude generiert 3 Bildideen, OpenAI erzeugt Bilder,
   Hosting via ImgBB                              (scripts/image_gen.py)
        │
        ▼
4. Telegram-Bot schickt die 3 Bilder + Buttons:
   1️⃣/2️⃣/3️⃣ Bild wählen   📤 Eigenes Bild hochladen
   🔄 Neue Vorschläge   ❌ Abbrechen
        │
   ┌────┴─────┬──────────────────┬───────────────────┐
   Bild wählen 📤 Eigenes Bild    🔄 Neue Vorschläge   ❌ / Timeout
        │      hochladen         (max. 2x)                │
        │         │                  │                    │
        ▼         ▼                  ▼                    ▼
   weiter zu 5.  Bild als Foto   zurück zu 3.        Workflow endet,
                 an den Chat                        nichts wird gepostet
                 senden → weiter
                 zu 5.
        │
        ▼
5. Ocoya erstellt den Post (Text + Bild) und plant ihn für den
   nächsten Tag, 10:00 Uhr (konfigurierbar), ein
        │
        ▼
6. Telegram-Nachricht zeigt "✅ Post eingeplant für <Datum/Zeit>!"
```

Es gibt **keinen separaten Server/Webhook** — der GitHub-Actions-Job selbst
pollt Telegram, solange er läuft (Job-Timeout: 180 Minuten, da bis zu 3
Warte-Phasen nacheinander bis zu je 60 Minuten dauern können).

---

## Schritt 1: Telegram-Bot über BotFather einrichten

1. Öffne Telegram, suche **@BotFather** und starte einen Chat.
2. Sende `/newbot` und folge den Anweisungen (Name + Username für den Bot wählen,
   Username muss auf `bot` enden, z.B. `MeineFirmaSocialBot`).
3. BotFather gibt dir ein **Bot-Token** zurück, z.B.
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — das ist dein
   `TELEGRAM_BOT_TOKEN`. Bewahre es sicher auf, es steht für vollen Zugriff auf
   den Bot.
4. Öffne einen Chat mit deinem neuen Bot und schicke ihm eine beliebige
   Nachricht (z.B. "Hallo"), damit er "weiß", wer du bist.
5. Ermittle deine **Chat-ID**, indem du im Browser diese URL aufrufst
   (Token einsetzen):
   ```
   https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates
   ```
   In der JSON-Antwort findest du `"chat":{"id":123456789, ...}` — diese Zahl
   ist deine `TELEGRAM_CHAT_ID`.
   - Falls die Antwort leer ist (`"result":[]`), hast du dem Bot noch keine
     Nachricht geschickt — Schritt 4 wiederholen und die URL erneut aufrufen.

## Schritt 2: Ocoya vorbereiten

1. In Ocoya unter **Workspace Settings → Developers → API** einen neuen
   API-Key erstellen → das ist `OCOYA_API_KEY`.
2. Verbinde in Ocoya deine Social-Media-Kanäle (Instagram, LinkedIn, Facebook, X),
   falls noch nicht geschehen.
3. Lokal (nicht in GitHub!) das Hilfsskript ausführen, um Workspace- und
   Profil-IDs zu ermitteln:
   ```bash
   pip install requests
   OCOYA_API_KEY=dein_key python scripts/list_ocoya_resources.py
   ```
   Notiere dir die Workspace-ID (`OCOYA_WORKSPACE_ID`).
4. Skript erneut mit gesetzter Workspace-ID ausführen, um die Social-Profile
   zu sehen:
   ```bash
   OCOYA_API_KEY=dein_key OCOYA_WORKSPACE_ID=deine_workspace_id \
     python scripts/list_ocoya_resources.py
   ```
   Notiere dir die IDs aller Profile, die bespielt werden sollen (Instagram,
   LinkedIn, Facebook, X) — komma-getrennt ergeben sie
   `OCOYA_SOCIAL_PROFILE_IDS`, z.B. `clh1abc,clh2def,clh3ghi,clh4jkl`.

## Schritt 3: Anthropic API-Key besorgen

1. Auf [console.anthropic.com](https://console.anthropic.com) einloggen (oder
   Account anlegen) und unter **API Keys** einen neuen Key erstellen → das
   ist `ANTHROPIC_API_KEY`.

## Schritt 3b: OpenAI und ImgBB für die Bildvorschläge einrichten

1. Auf [platform.openai.com](https://platform.openai.com/api-keys) einen neuen
   API-Key erstellen → das ist `OPENAI_API_KEY`. Die Bildgenerierung
   (`gpt-image-1`) wird pro erzeugtem Bild abgerechnet.
2. Auf [api.imgbb.com](https://api.imgbb.com/) einloggen (oder Account anlegen)
   und dort einen kostenlosen API-Key erstellen → das ist `IMGBB_API_KEY`.
   Darüber werden sowohl die KI-generierten Bildvorschläge als auch von dir
   hochgeladene eigene Bilder öffentlich gehostet, damit Ocoya sie abrufen kann
   (Ocoya akzeptiert nur öffentliche Bild-URLs, keine
   Datei-Uploads).

## Schritt 4: Marken-Briefing ausfüllen

Öffne [`config/brand.md`](config/brand.md) und fülle es aus (Marke, Zielgruppe,
Tonalität, erlaubte Themen, Format). Dieses Dokument steuert, worüber und wie
Claude schreibt — je konkreter, desto besser die Ergebnisse. Diese Datei landet
im Git-Repo (enthält keine Geheimnisse).

## Schritt 5: GitHub-Repo erstellen und Secrets hinterlegen

Das lokale Repo ist bereits vorbereitet (git init + erster Commit). Als
Nächstes:

1. Erstelle ein neues, **privates** Repository auf GitHub (über die Weboberfläche
   oder `gh repo create`, falls du die GitHub CLI installiert hast).
2. Verbinde das lokale Repo damit und push:
   ```bash
   git remote add origin https://github.com/<dein-user>/<dein-repo>.git
   git branch -M main
   git push -u origin main
   ```
3. Im GitHub-Repo unter **Settings → Secrets and variables → Actions → New
   repository secret** folgende Secrets anlegen (Werte aus den Schritten oben):

   | Secret-Name | Wert |
   |---|---|
   | `ANTHROPIC_API_KEY` | Anthropic API-Key |
   | `OPENAI_API_KEY` | OpenAI API-Key (Bildgenerierung) |
   | `IMGBB_API_KEY` | ImgBB API-Key (Bild-Hosting) |
   | `TELEGRAM_BOT_TOKEN` | Telegram Bot-Token |
   | `TELEGRAM_CHAT_ID` | Deine Telegram Chat-ID |
   | `OCOYA_API_KEY` | Ocoya API-Key |
   | `OCOYA_WORKSPACE_ID` | Ocoya Workspace-ID |
   | `OCOYA_SOCIAL_PROFILE_IDS` | Komma-getrennte Ocoya Social-Profile-IDs |

   **Wichtig:** Diese Werte werden nirgendwo im Code oder in Dateien im Klartext
   gespeichert — GitHub Actions injiziert sie zur Laufzeit als Umgebungsvariablen
   (siehe `.github/workflows/weekly-post.yml`).

## Schritt 6: Workflow testen

1. Im GitHub-Repo unter **Actions → Weekly Social Media Post → Run workflow**
   den Workflow manuell auslösen (`workflow_dispatch`).
2. Innerhalb weniger Sekunden solltest du im Telegram-Chat mit deinem Bot einen
   Text-Entwurf mit drei Buttons sehen.
3. Zum Testen einmal auf **🔄 Neu generieren** klicken (neuer Entwurf erscheint),
   danach auf **✅ Freigeben**.
4. Kurz danach schickt der Bot 3 KI-generierte Bildvorschläge sowie Buttons zur
   Auswahl. Wähle eins der Bilder, oder klicke auf **📤 Eigenes Bild hochladen**
   und schicke danach ein Foto in den Chat.
5. Der Post wird mit Text + gewähltem Bild über Ocoya eingeplant, und die
   Telegram-Nachricht zeigt "✅ Post eingeplant für ...!".
6. Den Fortschritt/Logs siehst du im GitHub-Actions-Lauf.

Danach läuft der Workflow automatisch jeden **Montag um 08:00 UTC**
(anpassbar über die `cron`-Zeile in `.github/workflows/weekly-post.yml`).

---

## Lokal testen (optional)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ausfüllen
export $(grep -v '^#' .env | xargs)
cd scripts
python main.py
```

## Konfiguration

| Umgebungsvariable | Bedeutung | Default |
|---|---|---|
| `POLL_TIMEOUT_MINUTES` | Wie lange pro Schritt auf deine Telegram-Antwort gewartet wird | `60` |
| `MAX_REGENERATIONS` | Max. Anzahl "Neu generieren"-Klicks (Text) pro Lauf | `4` |
| `MAX_IMAGE_REGENERATIONS` | Max. Anzahl "Neue Vorschläge"-Klicks (Bilder) pro Lauf | `2` |
| `POST_SCHEDULE_HOUR` | Uhrzeit (lokale Stunde), für die der Post am nächsten Tag eingeplant wird | `10` |
| `POST_SCHEDULE_TIMEZONE` | Zeitzone für `POST_SCHEDULE_HOUR` | `Europe/Berlin` |

Diese können in `.github/workflows/weekly-post.yml` unter `env:` angepasst werden.
Da die Warte-Phasen (Text-Freigabe, Bildauswahl, ggf. Foto-Upload) nacheinander
laufen, sollte `timeout-minutes` des Jobs großzügig über `POLL_TIMEOUT_MINUTES × 3`
plus Regenerations-Puffer liegen.

## Projektstruktur

```
config/brand.md              Marken-Briefing für Claude
scripts/generate_post.py     Anthropic API: generiert Thema/Caption/Hashtags + Bildideen
scripts/image_gen.py         OpenAI API: erzeugt Bilder, ImgBB: hostet sie öffentlich
scripts/telegram_bot.py      Telegram Bot API: senden, Buttons, Fotos empfangen, Long-Polling
scripts/ocoya_client.py      Ocoya API: Post erstellen + für Zeitpunkt einplanen
scripts/list_ocoya_resources.py   Einmaliges lokales Setup-Hilfsskript
scripts/main.py               Orchestriert den gesamten Ablauf
scripts/lead_finder.py        Lead-Recherche: Website/Impressum prüfen -> Master-Liste (siehe Abschnitt "Lead-Finder + Anrufliste")
scripts/lead_store.py         Persistente Master-Liste leads/leads.csv (Status, kein_interesse-Sperre, Wiedervorlage)
scripts/lead_caller.py        Wählt bis zu 5 Leads, erzeugt Gesprächsleitfaden, sendet Telegram-Karten mit Buttons
scripts/lead_status_poller.py Holt die Button-Klicks nach und schreibt sie in den Status zurück
prompts/voice_profile_b2b.md  Voice-Profil für den Gesprächsleitfaden (als system übergeben)
leads/                        Prospect-CSV + Master-Liste leads.csv (bis auf das Beispiel gitignored)
.github/workflows/weekly-post.yml  Wöchentlicher Cron-Job + manueller Trigger

scripts/daily/                 Eigenständiges tägliches Programm (kein Ocoya, keine Freigabe)
scripts/daily/generate_content.py  Anthropic API: Text + 3 Bildideen + Video-Overlay-Text
scripts/daily/image_gen.py     OpenAI API: erzeugt Bilder, Cloudinary hostet sie öffentlich
scripts/daily/video_gen.py     ffmpeg: rendert vertikales Reel/TikTok-Video aus den Bildern
scripts/daily/cloudinary_client.py  Bild-/Video-Hosting für alle Plattformen
scripts/daily/notify.py        Optionale Telegram-Ergebnis-Zusammenfassung (kein Gate)
scripts/daily/check_setup.py   Prüft Plattform-Credentials ohne zu posten
scripts/daily/publishers/      Ein Client je Plattform (meta, linkedin, twitter, tiktok)
scripts/daily/main.py          Orchestriert den gesamten täglichen Ablauf
.github/workflows/daily-post.yml   Täglicher Cron-Job + manueller Trigger
```

## Tägliche Automatisierung (direkte Plattform-APIs, ohne Freigabe)

Neben dem obigen wöchentlichen Freigabe-Workflow gibt es ein **zweites, komplett
unabhängiges Programm** unter [`scripts/daily/`](scripts/daily/): Es generiert
**täglich** per Claude einen Post (Text + 3 Bildideen), erzeugt daraus per OpenAI
3 Bilder sowie ein kurzes vertikales Reel/TikTok-Video (ffmpeg: Ken-Burns-Effekt +
Crossfades + Text-Overlay, kein Musik-Layer wegen Urheberrecht), und postet **direkt
über die jeweiligen Plattform-APIs** (Meta Graph API, LinkedIn, X, TikTok) — **ohne**
Ocoya und **ohne** manuellen Freigabeschritt. Läuft täglich über
[`.github/workflows/daily-post.yml`](.github/workflows/daily-post.yml).

**Wichtig, weil es keine Freigabe gibt:** Der generierte Text wird ungeprüft
veröffentlicht. `config/brand.md` (Tonalität, Tabu-Themen) wird zwar bei jedem Lauf
beachtet, aber es lohnt sich, die ersten Läufe engmaschig zu beobachten (Telegram-
Zusammenfassung, siehe unten) und ggf. `ENABLED_PLATFORMS` erstmal auf eine einzelne
Plattform zu beschränken.

### Warum direkte APIs mehr Aufwand bedeuten als Ocoya

Jede Plattform braucht eine **eigene Developer-App + eigenes Token**, die du selbst
einrichten musst (das kann ich nicht für dich per OAuth-Flow erledigen):

| Plattform | Aufwand | Einschränkung |
|---|---|---|
| **Instagram + Facebook** (Meta Graph API) | Meta-App (Typ "Business") anlegen, Instagram-Konto mit Facebook-Seite verbinden, Page-Access-Token generieren | Kein App Review nötig, solange du selbst Admin/Tester der App bist |
| **LinkedIn** | LinkedIn-App anlegen, Produkt "Share on LinkedIn" aktivieren, einmalig OAuth durchklicken | Self-Serve, kein Review — aber Access Token läuft nach **~60 Tagen** ab und muss manuell erneuert werden |
| **X (Twitter)** | Developer-App mit "Read and Write" + OAuth 1.0a anlegen | Free-Tier: 500 Posts/Monat (reicht für 1x täglich) |
| **TikTok** | Developer-App mit Produkt "Content Posting API" (Scope `video.publish`) anlegen | **Ohne App-Audit nur `SELF_ONLY`** (privater Entwurf, nur für dich sichtbar) — für öffentliches Posten ist ein TikTok-Audit nötig, das mehrere Tage dauern kann |

Du musst nicht alle vier einrichten — `ENABLED_PLATFORMS` bestimmt, welche
tatsächlich angesprochen werden.

### Einrichtung

1. **Cloudinary** (Bild- + Video-Hosting) unter [cloudinary.com](https://cloudinary.com/)
   registrieren (Free-Tier reicht), Cloud Name/API Key/API Secret notieren.
2. Für jede gewünschte Plattform die jeweilige Developer-App gemäß Tabelle oben
   einrichten und die Tokens besorgen (Docstrings in
   `scripts/daily/publishers/*.py` enthalten die genauen Setup-Schritte pro Datei).
3. Lokal testen, ohne dass irgendetwas gepostet wird:
   ```bash
   cd scripts/daily
   pip install -r ../../requirements.txt
   export $(grep -v '^#' ../../.env | xargs)   # .env vorher ausfuellen
   python main.py --dry-run
   ```
   Prüft, dass Text, Bilder und Video korrekt erzeugt werden.
4. Sobald erste Plattform-Tokens hinterlegt sind, Gültigkeit prüfen:
   ```bash
   python check_setup.py
   ```
5. Im GitHub-Repo unter **Settings → Secrets and variables → Actions**:
   - **Secrets:** alle in [`.env.example`](.env.example) gelisteten Keys/Tokens
     (`CLOUDINARY_*`, `META_*`, `LINKEDIN_*`, `X_*`, `TIKTOK_ACCESS_TOKEN`,
     optional `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` für die
     Ergebnis-Benachrichtigung).
   - **Variables:** `ENABLED_PLATFORMS` (z.B. `instagram_feed,linkedin`) und
     optional `TIKTOK_PRIVACY_LEVEL`.
6. Workflow **Daily Social Media Post** einmal manuell über `workflow_dispatch`
   auslösen und im Actions-Log sowie auf der echten Plattform prüfen, dass der
   Post ankommt.

Danach läuft der Workflow automatisch **jeden Tag um 08:00 UTC** (anpassbar über
die `cron`-Zeile in `.github/workflows/daily-post.yml`).

### Gültige `ENABLED_PLATFORMS`-Werte

`instagram_feed`, `instagram_reel`, `facebook_feed`, `facebook_video`,
`linkedin`, `linkedin_video`, `twitter`, `twitter_video`, `tiktok`
(komma-getrennt, beliebige Kombination).

## Lead-Finder + Anrufliste (eigenes Angebot akquirieren)

Recherche lokaler Betriebe mit schwacher Online-Präsenz und Aufbereitung als
**Telefon-Anrufliste** — kein Mailversand. Grund: Kalte Werbe-E-Mails brauchen im B2B
eine vorherige Einwilligung (§ 7 Abs. 2 UWG); telefonische Ansprache Gewerbetreibender
ist bei sachlichem Bezug über die mutmaßliche Einwilligung zulässig. Ob das für dein
konkretes Angebot trägt, bitte vorab anwaltlich klären.

**Vier Bausteine:**

1. **Recherche** — `scripts/lead_finder.py` liest eine Prospect-CSV (Name, Website,
   Branche, Region, `contact_name`, `phone`, `notes` — siehe
   [`leads/prospects.example.csv`](leads/prospects.example.csv)), ruft je Betrieb nur die
   öffentliche Website inkl. Impressum/Kontakt ab (kein Login, kein Social-Scraping),
   prüft Social-Verlinkung + Aktualität (Heuristik), **liest die Telefonnummer aus dem
   Impressum** (manuelle `phone`-Spalte hat Vorrang) und schreibt alles in die persistente
   Master-Liste `leads/leads.csv`.
2. **Leitfaden + Versand** — `scripts/lead_caller.py` wählt bis zu 5 anrufbare Leads
   (höchster Score zuerst, nur mit Nummer), erzeugt je einen **Gesprächsleitfaden** (vier
   Blöcke: Aufhänger / Was das praktisch heißt / zwei Rückfragen / wahrscheinlichster
   Einwand) und schickt pro Betrieb eine Telegram-Karte mit Nummer, Leitfaden und vier
   Buttons. Das Voice-Profil steht in [`prompts/voice_profile_b2b.md`](prompts/voice_profile_b2b.md)
   und wird als `system` übergeben — änderbar ohne Codeänderung.
3. **Status-Rückschrieb** — `scripts/lead_status_poller.py` holt die Button-Klicks
   (Erreicht / Nicht erreicht / Kein Interesse / Später) nach und schreibt sie in den
   Status zurück. Getrennt vom Versand, weil über den Tag verteilt geklickt wird.
4. **Master-Liste** — `leads/leads.csv` ist die einzige Quelle der Wahrheit (Status,
   `angerufen_am`, Notiz, Wiedervorlage). **`kein_interesse` sperrt dauerhaft** — wer einmal
   ablehnt, erscheint nie wieder auf der Liste.

```bash
python scripts/lead_finder.py leads/prospects.csv       # Recherche -> Master-Liste aktualisieren
python scripts/lead_caller.py --dry-run                  # Leitfäden nur anzeigen (Testlauf, nichts senden)
python scripts/lead_caller.py --limit 5                  # bis zu 5 Anruf-Karten nach Telegram
python scripts/lead_status_poller.py                     # Klicks einmal abarbeiten
python scripts/lead_status_poller.py --watch 300         # 5 Minuten lauschen
```

### Zeitplan (lokal, nicht GitHub Actions)

Bewusst **lokal** (z.B. Windows-Aufgabenplanung), nicht als GitHub-Actions-Cron: Die
Master-Liste enthält personenbezogene Kontaktdaten, ist per `.gitignore` vom Commit
ausgeschlossen und muss über Läufe hinweg erhalten bleiben. Actions-Runner sind flüchtig —
ein verlorener Zustand würde die `kein_interesse`-Sperre aushebeln (genau das rechtliche
Risiko). Anrufe passieren ohnehin am Rechner.

Empfehlung (Anrufe 9–17 Uhr, werktags):
- **Morgens werktags** `lead_finder.py` (falls neue Prospects) **und** `lead_caller.py`.
- **Stündlich 9–17 Uhr werktags** `lead_status_poller.py`.

Windows-Aufgabenplanung, Beispiel für den Sende-Lauf (werktags 9:00):

```powershell
$py = (Get-Command python).Source
schtasks /Create /TN "LeadCaller" /TR "$py `"$PWD\scripts\lead_caller.py`"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:00
schtasks /Create /TN "LeadPoller" /TR "$py `"$PWD\scripts\lead_status_poller.py`"" /SC HOURLY /MO 1 /ST 09:00 /ET 17:00 /K
```

(`.env` mit `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` muss geladen sein;
neue Secrets braucht es nicht.) Auf macOS/Linux entsprechend `cron` mit `07:00 UTC` (Sommer)
bzw. `08:00 UTC` (Winter), da Cron dort ggf. in UTC läuft.

**Datenschutz:** `leads/leads.csv` und der Poller-Offset `leads/.tg_offset` sind per
`.gitignore` vom Commit ausgeschlossen; nur `leads/prospects.example.csv` wird versioniert.

## Webseiten-Optimierer (Analyse + neu designte Version)

`scripts/website_optimizer.py` analysiert eine beliebige Webseite und erstellt daraus
eine professionell neu designte, mobile-optimierte Version — nützlich z.B. um Leads aus
dem Lead-Finder eine konkrete "Vorher/Nachher"-Vorschau zu zeigen.

**Wie es funktioniert:**
1. Das Skript lädt die Webseite und misst Technik-Werte (Ladezeit, Seitengröße,
   Mobil-Tauglichkeit, SEO-Basics, Bildgrößen, render-blockierende Skripte).
2. Claude bewertet Design, Mobil-Darstellung, Geschwindigkeit und SEO mit Schulnoten
   und schreibt einen verständlichen Bericht mit priorisiertem Maßnahmenplan
   (`bericht.md`).
3. Claude baut aus den **echten Inhalten** der Seite (Texte, Bilder, Navigation,
   Kontaktdaten — nichts wird dazuerfunden) eine komplett neue, moderne HTML-Seite
   (`neue-webseite.html`), die man direkt im Browser öffnen kann.

```bash
python scripts/website_optimizer.py https://beispiel-firma.de                 # Bericht + Redesign
python scripts/website_optimizer.py https://beispiel-firma.de --nur-analyse   # nur Bericht
```

Die Ergebnisse landen in `website_optimierung/<domain>_<datum>/`. Benötigt nur den
`ANTHROPIC_API_KEY` (in der `.env` oder als Umgebungsvariable).

**Wichtig:** Eine fremde Live-Webseite kann das Skript nicht direkt verändern — dafür
bräuchte man Zugriff auf deren Hosting. Die erzeugte HTML-Datei ist eine fertige
Vorlage/Vorschau, die man hochladen oder dem Kunden präsentieren kann.

## Sicherheit

- Alle API-Keys/Tokens liegen ausschließlich als **GitHub Actions Secrets** vor,
  niemals im Code oder in Git-History.
- `.env` ist in `.gitignore` und wird nie committet.
- Der Ocoya-API-Key erlaubt server-seitigen Zugriff auf deinen Workspace —
  wie jeden API-Key nicht in Client-Code oder öffentlichen Repos verwenden.

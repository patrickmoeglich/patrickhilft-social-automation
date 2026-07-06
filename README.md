# Wöchentliche Social-Media-Automatisierung

Jeden Montag generiert Claude (Anthropic API) einen Post-Entwurf, schickt ihn dir
per Telegram-Bot zur Freigabe, und veröffentlicht ihn nach deinem "✅ Freigeben"
über [Ocoya](https://ocoya.com) auf Instagram, LinkedIn, Facebook und X.
Alles läuft in einem einzigen GitHub-Actions-Workflow — kein eigener Server nötig.

## Wie der Ablauf funktioniert

```
GitHub Actions (Montag, 08:00 UTC oder manuell)
        │
        ▼
1. Claude generiert Thema + Caption + Hashtags   (scripts/generate_post.py)
        │
        ▼
2. Telegram-Bot schickt Entwurf mit Buttons:
   ✅ Freigeben   🔄 Neu generieren   ❌ Abbrechen  (scripts/telegram_bot.py)
        │
        ▼
3. Workflow wartet (Long-Polling, bis zu 60 Min.) auf deine Antwort
        │
   ┌────┴─────────────┬──────────────────┐
   ✅ Freigeben        🔄 Neu generieren   ❌ / Timeout
        │                  │                  │
        ▼                  ▼                  ▼
4. Ocoya postet    zurück zu Schritt 1    Workflow endet,
   auf allen        (max. 4x)             nichts wird gepostet
   Plattformen           
        │
        ▼
5. Telegram-Nachricht wird zu "✅ Veröffentlicht!" bearbeitet
```

Es gibt **keinen separaten Server/Webhook** — der GitHub-Actions-Job selbst
pollt Telegram, solange er läuft (Job-Timeout: 75 Minuten).

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
   Post-Entwurf mit drei Buttons sehen.
3. Zum Testen einmal auf **🔄 Neu generieren** klicken (neuer Entwurf erscheint),
   danach auf **✅ Freigeben** — der Post wird über Ocoya veröffentlicht und die
   Telegram-Nachricht zeigt "✅ Veröffentlicht!".
4. Den Fortschritt/Logs siehst du im GitHub-Actions-Lauf.

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
| `POLL_TIMEOUT_MINUTES` | Wie lange auf deine Telegram-Antwort gewartet wird | `60` |
| `MAX_REGENERATIONS` | Max. Anzahl "Neu generieren"-Klicks pro Lauf | `4` |

Diese können in `.github/workflows/weekly-post.yml` unter `env:` angepasst werden.

## Projektstruktur

```
config/brand.md              Marken-Briefing für Claude
scripts/generate_post.py     Anthropic API: generiert Thema/Caption/Hashtags
scripts/telegram_bot.py      Telegram Bot API: senden, Buttons, Long-Polling
scripts/ocoya_client.py      Ocoya API: Post erstellen + sofort veröffentlichen
scripts/list_ocoya_resources.py   Einmaliges lokales Setup-Hilfsskript
scripts/main.py               Orchestriert den gesamten Ablauf
.github/workflows/weekly-post.yml  Wöchentlicher Cron-Job + manueller Trigger
```

## Sicherheit

- Alle API-Keys/Tokens liegen ausschließlich als **GitHub Actions Secrets** vor,
  niemals im Code oder in Git-History.
- `.env` ist in `.gitignore` und wird nie committet.
- Der Ocoya-API-Key erlaubt server-seitigen Zugriff auf deinen Workspace —
  wie jeden API-Key nicht in Client-Code oder öffentlichen Repos verwenden.

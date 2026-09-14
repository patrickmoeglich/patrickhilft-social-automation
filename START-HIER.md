# Webseiten-Optimizer — Start auf diesem PC (Stand 03.08.2026)

Dieses Projekt kam am 03.08.2026 frisch von GitHub auf diesen PC
(`github.com/patrickmoeglich/patrickhilft-social-automation`, Stand 30.07.2026).
Es enthält zwei getrennte Dinge:

1. **Webseiten-Optimizer** (`scripts/website_optimizer.py`) — schaut sich eine
   bestehende Webseite an, schreibt einen Bericht auf Deutsch und baut eine neu
   gestaltete Version als eine HTML-Datei. **Braucht nur den Anthropic-Schlüssel,
   der auf diesem PC schon gesetzt ist.**
2. **Social-Media-Automatisierung** (übrige Skripte) — läuft über GitHub Actions,
   braucht die `.env` mit Telegram-, Ocoya-, OpenAI- und ImgBB-Schlüsseln. Die
   liegt nur auf dem Mac bzw. in OneDrive (`Vom-Mac\Desktop\Work\...\.env`) und
   wird für den Optimizer NICHT benötigt.

## Optimizer starten

Am einfachsten: Doppelklick auf **`optimizer-start.cmd`** — fragt nach der
Adresse, installiert beim ersten Mal die Pakete, öffnet danach den Ergebnisordner.

Von Hand (PowerShell, neues Fenster):

```
cd C:\Users\Anwender\Projekte\patrickhilft-social-automation
py -3 -m pip install -r requirements.txt        (nur beim ersten Mal)
py -3 scripts\website_optimizer.py https://beispiel-firma.de
```

Nur Bericht, ohne neue Seite: `--nur-analyse` anhängen.

## Ergebnis

Pro Lauf entsteht `website_optimierung\<domain>_<datum>\` mit `bericht.md`
(verständliche Bewertung) und `neue-webseite.html` (fertige Neuversion zum
Verschicken als Vorschau). Alte Läufe von Juli (baeckerbluem.de, alzey-teilhabe.de,
patrickhilft.de) liegen teils schon im Ordner.

## Zwei Hinweise

- Das Modell wurde am 03.08.2026 auf `claude-opus-5` umgestellt (Zeile 37 im
  Skript) — dasselbe wie in webgen. Diese Änderung ist noch nicht auf GitHub
  gesichert.
- Änderungen am Code danach per GitHub Desktop oder `git push` sichern, damit
  Mac und PC nicht wieder auseinanderlaufen.

## Verhältnis zu webgen

webgen (`C:\Users\Anwender\Projekte\webgen`) baut aus einem Briefing eine NEUE
Seite; dieser Optimizer verbessert BESTEHENDE Seiten. Zusammen decken sie beide
Kundenfälle ab — Bericht des Optimizers als Einstieg beim Kunden, webgen für den
Neubau.

---
name: tool-radar
description: Wöchentlicher Radar für neue MCP-Server, Claude Skills und vergleichbare Erweiterungen. Prüft feste Quellen, filtert hart auf Patricks Projekte (patrickhilft.de, B2B-Agentur, Vita Nova), führt Buch in tool-radar-gesehen.json und meldet per Telegram. Nutzen, wenn der Nutzer "Tool-Radar", "was gibt es Neues an MCP/Skills", oder den Montags-Lauf anstößt.
---

# Tool-Radar

Findet neue Erweiterungen, die Patrick wirklich nützen. Der Maßstab ist streng:
**lieber "diese Woche nichts" melden als schwache Treffer.** Ein schwacher Treffer
kostet Patrick Prüfzeit und macht den Radar langfristig wertlos.

## Ablage

| Zweck | Pfad |
|---|---|
| Gedächtnis | `C:\Users\Anwender\Documents\patrickhilft-social-automation\tool-radar-gesehen.json` |
| Modul (Gedächtnis + Versand) | `...\scripts\tool_radar.py` |
| Tests | `...\scripts\test_tool_radar.py` |

Python immer über `.venv\Scripts\python.exe` des Repos aufrufen.

## Kontext zu Patrick

Solo-Selbstständiger in Osthofen (Rheinhessen), **kein Team**. Zwei Standbeine:

1. **patrickhilft.de** — persönliche Assistenz, 24-Stunden-Betreuung, barrierefreie
   Mobilität (V-Klasse mit Rollstuhllift)
2. **B2B-Agentur** — Web und Social Media für lokale Betriebe

In Planung: **Vita Nova**, Premium-Tagespflege, Start 2027/2028 im Wonnegau.

Stack: Claude Code, Cloudflare Worker, Telegram-Bot, Resend, Neon/PostgreSQL,
sevdesk, Gmail/Drive/Calendar. Grundsatz: **Local-First, Kundendaten bleiben
lokal, DSGVO-konform.**

## Quellen — bei jedem Lauf alle prüfen

1. Offizielles MCP-Registry (`registry.modelcontextprotocol.io`)
2. Anthropic Changelog / Release Notes (Claude Code, Skills, Connectors)
3. Anthropic Skills-Dokumentation und öffentliche Skill-Sammlungen
   (u. a. `github.com/anthropics/skills`)
4. GitHub: `punkpeye/awesome-mcp-servers` und vergleichbare kuratierte Listen
5. Smithery (`smithery.ai`)
6. `mcpservers.org` bzw. ein gleichwertiges Verzeichnis

**Nicht erreichbare Quelle niemals stillschweigend überspringen.** Sie kommt in
den Report unter „Quellen nicht erreichbar" mit Grund (Timeout, 404, Paywall).

### Domains

Der Montagslauf ist headless und kann keine Berechtigung erfragen — eine
Rückfrage wird still abgelehnt und die Quelle erscheint fälschlich als „nicht
erreichbar". Die Freigaben stehen deshalb als `--allowedTools` in
`scripts/tool_radar_montagslauf.cmd`.

> **Wird die Quellenliste oben geändert, muss die Domainliste unten und damit
> `scripts/tool_radar_montagslauf.cmd` mitgepflegt werden.** Der Test
> `test_domains_in_skill_und_wrapper_sind_synchron` schlägt sonst an.

Der folgende Block wird maschinell ausgelesen — ein Eintrag pro Zeile, keine
Kommentare, kein Markup:

<!-- domains:start -->
registry.modelcontextprotocol.io
github.com
raw.githubusercontent.com
api.github.com
smithery.ai
mcpservers.org
code.claude.com
platform.claude.com
<!-- domains:end -->

## Filter

### Stufe 0 — Dedupe gegen das Gedächtnis

Für jeden Kandidaten `pruefe(daten, name, quelle, stand)` aufrufen. `stand` ist das
Datum des letzten Commits oder Releases im Format `YYYY-MM-DD`.

- `neu` → weiter zu Stufe 1
- `update` → weiter zu Stufe 1, im Report als **„Update"** kennzeichnen und
  dazuschreiben, *was* sich geändert hat. Nur melden, wenn die Änderung einen
  Cluster betrifft — ein Doku-Tippfehler ist kein Update.
- `bekannt` → verwerfen, nicht erneut recherchieren

### Stufe 1 — Harte K.o.-Kriterien

Ein Treffer hier fliegt raus, **ohne** Punktebewertung. Im Gedächtnis als
`status: "ausgeschlossen"` mit Grund ablegen.

- Setzt Team, Seats oder „contact sales" voraus
- Zwingt Kundendaten zu einem fremden Anbieter, obwohl die Aufgabe lokal lösbar
  wäre. Fachlich unvermeidbar ist erlaubt (z. B. eine Kassen- oder Behörden-API)
- Letzter Commit älter als **6 Monate** *oder* kein erkennbarer Maintainer/Organisation
- Kein Geschäftsnutzen erkennbar (Spielerei)

### Stufe 2 — Cluster-Pflicht

Mindestens ein Cluster muss getroffen sein. Kein Cluster = kein Treffer, auch bei
objektiv gutem Tool. Das hält generische „coole MCP-Server" draußen.

1. Pflege, Betreuung, Assistenz, Hilfsmittel, Abrechnung mit Kassen
2. Buchhaltung, Steuern, Rechnungswesen (Anbindung an sevdesk)
3. Lead-Generierung und Vertrieb im lokalen B2B
4. Content, Social Media, Bild- und Videogenerierung
5. Dokumente, Formulare, Behördenkram
6. Automatisierung/Infrastruktur, die den bestehenden Stack verbessert
7. Nützlich für die Tagespflege-Gründung (Vita Nova)

### Stufe 3 — Nutzwert-Score 0–10

| Kriterium | Punkte |
|---|---|
| Direkter Anschluss an den Stack (sevdesk, Telegram, Cloudflare, Neon, Resend, Google) | 0–3 |
| Realistische Zeitersparnis pro Woche | 0–3 |
| Einrichtungsaufwand *invers* (< 1 h = 2, halber Tag = 1, mehr = 0) | 0–2 |
| Läuft lokal / self-hostbar | 0–2 |

**Meldeschwelle: ≥ 5.** Alles darunter kommt als `status: "zu_schwach"` ins
Gedächtnis und wird nie gemeldet. Bei einem späteren neuen Release wird es
automatisch erneut bewertet (`pruefe` gibt dann `neu` zurück).

## Ausgabeformat

Reiner Text, handytauglich: kurze Absätze, **keine Tabellen**, keine Markdown-
Sternchen (Telegram-Versand läuft ohne parse_mode). Sortiert nach Score absteigend.

Je Treffer:

```
1. <Name> — <Score>/10
   <URL>
   Was: <ein Satz>
   Für dich: <welches Projekt, wofür genau>
   Aufwand: <Zeit>, <Kosten oder "kostenlos">
   Risiko: <lokal oder gehostet>, <welche Daten rausgehen>
```

**Regellauf: maximal 5 Treffer.** Beim allerersten Lauf (Bestandsaufnahme) mehr
erlaubt, dann nach Cluster gruppiert.

Kein Treffer über der Schwelle:

```
Tool-Radar <Datum>: diese Woche nichts.
Geprüft: <n> Kandidaten aus <m> Quellen.
```

Keine Füllsätze, keine Entschuldigung, keine „Erwähnenswert am Rande"-Sektion.

Am Ende immer, falls zutreffend:

```
Quellen nicht erreichbar: <Quelle> (<Grund>)
```

## Ablauf

1. Gedächtnis laden und Größe melden
2. Alle sechs Quellen abfragen, Ausfälle notieren
3. Kandidaten durch Stufe 0 → 1 → 2 → 3
4. Report bauen
5. Versand — entscheidet sich am **Argument**, nicht am vermuteten Modus:
   - **Ohne Argument** (Patrick tippt `/tool-radar`): Report im Terminal zeigen
     und auf sein OK warten. Der Versand geht an sein Telefon, das wird nicht
     ungefragt ausgelöst.
   - **Argument `headless`** (Montagslauf aus der Aufgabenplanung, Aufruf
     `claude -p "/tool-radar headless"`): **sofort senden, nicht fragen.** Es
     ist niemand da, der antworten könnte — eine Rückfrage lässt den Lauf
     ergebnislos enden. Die Freigabe liegt in der Einrichtung der Aufgabe.
     Danach Gedächtnis fortschreiben, dann erst beenden.

   Nie am Modus raten. Steht `headless` nicht im Aufruf, wird gefragt.
6. Senden:
   `.venv\Scripts\python.exe scripts\tool_radar.py senden < report.txt`
7. Gedächtnis mit **allen** bewerteten Kandidaten fortschreiben (auch den
   verworfenen) und speichern

## Dauerhaft abgelehnte Tools

Ein Eintrag mit `dauersperre: true` wird nie wieder gemeldet, auch nicht nach
einem neuen Release. `pruefe()` gibt dafür immer `bekannt` zurück. Diese Sperre
setzt nur Patrick, nie der Radar von sich aus.

## Wichtig

- Nichts erfinden. Jeder Treffer braucht eine URL, die tatsächlich abgerufen wurde.
- Score und Aufwand sind Schätzungen — als solche benennen, nicht als Messwerte.
- Patrick prüft jedes Tool vor der Installation durch seinen Drittanbieter-Tool-Check.
  Der Radar empfiehlt, er installiert nichts und schlägt keine Installation vor.

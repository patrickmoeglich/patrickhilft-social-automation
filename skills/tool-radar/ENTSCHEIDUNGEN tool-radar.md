# ENTSCHEIDUNGEN — Tool-Radar

Wird nur ergänzt, nie überschrieben. Neueste oben.

## 24.08.2026 — Adeu 3.0.0 eingerichtet, Version festgenagelt

**Entschieden:** Adeu (DOCX-Redlining mit echter Word-Änderungsverfolgung) als
MCP-Server unter Windows eingerichtet, User-Scope, Version auf `adeu==3.0.0`
gepinnt. Dazu das Claude-Code-Plugin `adeu-redlining@adeu-skills`.

**Grund für den Pin:** Die offizielle Anleitung empfiehlt `npx -y` bzw.
`uvx --from adeu` ohne Version — dann läuft immer die neueste. Der Tool-Check
gilt aber nur für die geprüfte Version. Updates sollen bewusst passieren.

**Tool-Check-Ergebnis (Version 3.0.0):** Freigegeben. Im veröffentlichten
PyPI-Paket kein einziger HTTP-Client-Aufruf, keine Telemetrie, keine
Monetarisierungs-Begriffe. Plugin setzt keine Hooks, keine Statuszeile, keine
`permissions.allow`-Einträge. Einzige externe Adresse: Google Fonts in einer
optionalen HTML-Ansicht, die Claude Code nicht nutzt. Die Zeile
"Deploy free: horizon.prefect.io" beim Start ist ein Werbebanner des
Frameworks FastMCP — reiner Bildschirmtext, kein Netzwerkaufruf.
Nicht vollständig geprüft: das gebündelte Node-Paket (nur gegrept), und die
Abhängigkeit `fastmcp 4.0.0b1`.

**Funktionstest bestanden** an einer Kopie von "Dienstleistungsvertrag über
Alltagsassistenz und Präsenzbegleitung.docx": `numbering.xml` und `styles.xml`
semantisch identisch, 35 Absätze vorher wie nachher, hinzugekommen nur zwei
Redlines und drei Kommentare.

**Verworfen: der ursprüngliche Anwendungsfall.** Der Radar hatte Adeu für
Vita Nova vorgeschlagen (Trägerkonzept, Pacht-, Versorgungsvertrag). Das
Projekt ruht seit Mitte Juli — der Grund für die Auswahl war hinfällig, bevor
etwas damit gemacht wurde.

**Stattdessen, aber ungeprüft:** Der Test lief an einem echten
patrickhilft.de-Vertrag. Der Anwendungsfall existiert also dort, nicht bei
Vita Nova. Ob Patrick das so nutzen will, ist nicht entschieden.

## 24.08.2026 — Wochenentscheid: sonst nichts

Von vier Radar-Treffern wurde nur Adeu umgesetzt. Geparkt:
Cross-session messaging (kommt automatisch, ab Version 2.1.239 da),
`/design` (dran beim nächsten Agentur-Layout zur Kundenabstimmung),
Germany Tenders MCP (dran, wenn das Repo Betriebsdauer hat oder selbst
gehostet wird — 0 Sterne, Repo seit Juli 2026).

## 24.08.2026 — Offener Fund aus dem Radar-Lauf, nicht entschieden

Ein juristischer Hinweis aus dem Adeu-Testlauf: In § 1 Abs. 2 des
Dienstleistungsvertrags wurde eine Formulierung als
Scheinselbstständigkeits-Indiz markiert. Nicht bewertet, gehört vor einen
Anwalt.

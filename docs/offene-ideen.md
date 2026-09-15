# Offene Ideen

Beobachtungen, die aufbewahrt gehören, aber keine Aufgabe sind. Nichts hier ist
eingeplant, terminiert oder zugesagt.

---

## Lücke: keine MCP-Werkzeuge für Pflege, Assistenz und Kassenabrechnung

**Festgestellt:** 21.08.2026, erster Lauf des Tool-Radars
**Betrifft:** Vita Nova, mittelbar auch patrickhilft.de
**Status:** offene Idee, keine Aufgabe

### Was der Radar gefunden hat

Beim Durchsuchen von MCP-Registry, awesome-mcp-servers, Smithery,
mcpservers.org und den öffentlichen Skill-Sammlungen gab es für das
Themencluster *Pflege, Betreuung, Assistenz, Hilfsmittel, Abrechnung mit
Kassen* keinen einzigen brauchbaren Treffer.

Was es gibt, geht in zwei andere Richtungen:

- **US-Abrechnungskodierung** — ICD-10, CPT, HCPCS, RVU-Preise. Gebaut für das
  amerikanische Versicherungssystem, ohne Bezug zu SGB XI oder deutschen
  Pflegekassen.
- **Klinische Interoperabilität** — FHIR, HL7v2, DICOM, SNOMED. Gedacht für
  Krankenhäuser und EHR-Systeme, nicht für ambulante Assistenz oder Tagespflege.

Dazwischen, also bei allem was ein kleiner deutscher Anbieter täglich braucht,
ist nichts.

### Warum das notiert wird

Das ist kein Suchfehler und vermutlich auch keine Frage der Zeit. Der Markt für
MCP-Server folgt bislang dem angelsächsischen SaaS-Ökosystem; deutsche
Pflegeabrechnung ist dafür zu klein und zu reguliert.

Für Vita Nova heißt das: auf ein fertiges Werkzeug zu warten ist keine
Strategie. Wenn dort etwas gebraucht wird, muss es selbst gebaut werden. Der
Skill `mcp-builder` aus dem Anthropic-Repository wäre der Einstieg dafür.

### Wenn es irgendwann konkret wird

Was ein eigener Server abdecken könnte, grob und unsortiert:

- Leistungskomplexe und Vergütungssätze nachschlagen (landesspezifisch, ändert
  sich jährlich)
- Betreuungsdokumentation strukturiert erfassen, ePA-fähig ab 2026
- Anträge und Formulare gegenüber Pflegekassen vorbereiten
- Dienst- und Tourenplanung

Vorher zu klären wäre, was davon überhaupt Software sein sollte und was besser
Papier oder ein Telefonat bleibt.

### Nicht vergessen

Sobald sich hier etwas bewegt, meldet es der Radar von selbst — das Cluster
*Pflege* ist im Filter aktiv und wird bei jedem Lauf mitgeprüft.

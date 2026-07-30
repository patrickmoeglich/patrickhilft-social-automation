"""Generates a social media post draft (topic, caption, hashtags) via the Anthropic API."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import anthropic

MODEL = "claude-opus-4-8"
BRAND_FILE = Path(__file__).resolve().parent.parent / "config" / "brand.md"

# Feste Themenliste aus den drei Leistungsbereichen von patrickhilft.de.
# Es wird pro Woche automatisch EIN Thema ausgewaehlt (siehe _pick_weekly_topic),
# damit sich die Posts abwechseln und nicht immer dasselbe Thema kommt.
WEEKLY_TOPICS = [
    "Haushaltshilfe: Unterstuetzung beim Putzen, Aufraeumen und bei der Waesche im Alltag",
    "Einkaeufe und Botengaenge abnehmen, wenn der Weg zum Supermarkt schwerfaellt",
    "Alltagsbegleitung: Gesellschaft leisten und Zeit gegen Einsamkeit schenken",
    "Gemeinsame Spaziergaenge an der frischen Luft",
    "Gassi-Service und Hilfe mit Haustieren (Hunde, Katzen, Kleintiere)",
    "Begleitung zu Aemtern und Behoerden - Termine gemeinsam meistern",
    "Sichere Fahrten mit dem behindertengerechten V-Class inkl. Rollstuhl-Hublift",
    "Entlastung fuer pflegende Angehoerige - eine verlaessliche Auszeit",
    "Begleitung zu Arztterminen und Untersuchungen",
    "Persoenliche Betreuung: da sein, zuhoeren, den Tag strukturieren",
    "Unterstuetzung fuer Familien im turbulenten Alltag",
    "Flexible Alltagshilfe - individuell nach Bedarf statt Standardpaket",
]

# Zaehlt hoch, wenn im selben Lauf per "Neu generieren" ein anderer Entwurf angefordert wird,
# damit dann auch ein anderes Thema gewaehlt wird (nicht nur eine andere Formulierung).
_topic_offset = 0


def _pick_weekly_topic(regenerating: bool) -> str:
    """Waehlt das Thema fuer diese Woche. Bei 'Neu generieren' rueckt es ein Thema weiter."""
    global _topic_offset
    if regenerating:
        _topic_offset += 1
    week = datetime.now(ZoneInfo("Europe/Berlin")).isocalendar().week
    return WEEKLY_TOPICS[(week + _topic_offset) % len(WEEKLY_TOPICS)]


OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "Kurzer Titel des gewählten Themas"},
        "caption": {"type": "string", "description": "Fertiger Post-Text inkl. Call-to-Action, ohne Hashtags"},
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-6 relevante Hashtags ohne '#' Zeichen",
        },
    },
    "required": ["topic", "caption", "hashtags"],
    "additionalProperties": False,
}


def _build_prompt(topic_hint: str, feedback: Optional[str]) -> str:
    prompt = (
        "Erstelle einen neuen Social-Media-Post-Entwurf für diese Woche.\n\n"
        f"Das Thema für diesen Post ist fest vorgegeben:\n{topic_hint}\n\n"
        "Schreibe konkret und lebendig zu genau diesem Thema. Bleib beim vorgegebenen Thema "
        "und weiche nicht automatisch auf Arzttermine oder Fahrdienste aus, wenn das Thema "
        "etwas anderes vorgibt. Halte dich strikt an Tonalität und Format-Vorgaben aus dem Briefing."
    )
    if feedback:
        prompt += (
            "\n\nDer vorherige Entwurf wurde abgelehnt. Feedback dazu: "
            f"\"{feedback}\"\nBerücksichtige dieses Feedback und wähle einen anderen "
            "Blickwinkel als zuvor."
        )
    return prompt


# Bildmodelle treffen weder die Formensprache noch die Premium-Anmutung einer echten
# V-Klasse; das Ergebnis wirkt generisch statt hochwertig. Dazu kamen im Test Fremdlogos am
# Kuehlergrill und physikalisch falsche Rampengeometrien. Das Fahrzeug bleibt daher aus
# KI-Bildern komplett draussen - echte Fotos folgen, sobald welche vorliegen.
NO_VEHICLE_RULE = (
    "Harte Einschraenkung fuer alle 3 Bildideen: Das Fahrzeug darf NICHT vorkommen - weder "
    "Aussenansicht noch Innenraum, Cockpit oder Lenkrad, weder angeschnitten noch unscharf "
    "im Hintergrund. Das schliesst Anbauteile wie Hublift und Rampe mit ein. Es gilt auch "
    "dann, wenn das Thema des Posts das Fahrzeug ausdruecklich nennt. Weiche in dem Fall auf "
    "Umgebung, Personen oder Details ohne Fahrzeugbezug aus, z.B. ein ruhiger Weg zur "
    "Haustuer, Haende beim Tragen einer Einkaufstasche, ein Flur vor der Praxistuer, eine "
    "Strasse im Herbstlicht. Beschreibe Fahrzeug und Anbauteile in den englischen Prompts "
    "gar nicht erst - verlasse dich NICHT auf Negativ-Formulierungen wie 'no car' oder "
    "'without vehicle', denn Bildmodelle erzeugen genannte Objekte trotz Verneinung haeufig "
    "trotzdem."
)

# Anthropics json_schema-Output unterstuetzt fuer Arrays nur minItems/maxItems von 0 oder 1,
# daher werden die 3 Bildideen als einzelne Felder statt als Array fester Laenge modelliert.
IMAGE_PROMPTS_SCHEMA = {
    "type": "object",
    "properties": {
        "image_prompt_1": {
            "type": "string",
            "description": "Bildidee 1: konkrete Bildbeschreibung auf Englisch fuer ein Bildgenerierungsmodell",
        },
        "image_prompt_2": {
            "type": "string",
            "description": "Bildidee 2: unterscheidet sich von Idee 1 in Motiv, Perspektive oder Stil",
        },
        "image_prompt_3": {
            "type": "string",
            "description": "Bildidee 3: unterscheidet sich von Idee 1 und 2 in Motiv, Perspektive oder Stil",
        },
    },
    "required": ["image_prompt_1", "image_prompt_2", "image_prompt_3"],
    "additionalProperties": False,
}


def _system_prompt(brand_brief: str) -> list:
    return [
        {
            "type": "text",
            "text": (
                "Du bist Social-Media-Manager der folgenden Marke. Halte dich exakt an "
                "dieses Briefing:\n\n" + brand_brief
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def generate_post(feedback: Optional[str] = None) -> dict:
    """Returns {"topic": str, "caption": str, "hashtags": list[str]}."""
    brand_brief = BRAND_FILE.read_text(encoding="utf-8")
    topic_hint = _pick_weekly_topic(regenerating=feedback is not None)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_system_prompt(brand_brief),
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": _build_prompt(topic_hint, feedback)}],
    )

    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def generate_image_prompts(topic: str, caption: str, feedback: Optional[str] = None) -> list:
    """Returns 3 English image-generation prompts matching the given post."""
    brand_brief = BRAND_FILE.read_text(encoding="utf-8")

    prompt = (
        "Erstelle 3 unterschiedliche Bildideen (als Prompts fuer ein KI-Bildgenerierungsmodell, "
        "auf Englisch) fuer folgenden Social-Media-Post:\n\n"
        f"Thema: {topic}\nCaption: {caption}\n\n"
        "Die 3 Vorschlaege sollen sich in Motiv, Perspektive oder Stil unterscheiden, aber alle "
        "zum Markenbriefing passen.\n\n"
        + NO_VEHICLE_RULE
    )
    if feedback:
        prompt += f"\n\nFeedback zu den vorherigen Vorschlaegen: \"{feedback}\""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_system_prompt(brand_brief),
        output_config={"format": {"type": "json_schema", "schema": IMAGE_PROMPTS_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )

    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return [data["image_prompt_1"], data["image_prompt_2"], data["image_prompt_3"]]


if __name__ == "__main__":
    print(json.dumps(generate_post(), indent=2, ensure_ascii=False))

"""Generates a daily social media post draft (topic, caption, hashtags, 3 image
prompts) via the Anthropic API in a single call - no approval/regeneration loop,
since this pipeline runs fully automatically."""
import json
import os
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-8"
BRAND_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "brand_zwischen_den_zeilen.md"

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
        "card_question": {
            "type": "string",
            "description": (
                "Die Hook-Frage in Kurzform fuer die Bildkarte: ohne 'Erzähl mal', "
                "als direkte Frage mit Fragezeichen, max. 10 Woerter, "
                "z.B. 'Wann hast du zuletzt zu schnell geurteilt?'"
            ),
        },
    },
    "required": [
        "topic",
        "caption",
        "hashtags",
        "card_question",
    ],
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


def generate_daily_content() -> dict:
    """Returns topic/caption/hashtags plus card_question (the short hook
    question rendered onto the fixed story-card image)."""
    brand_brief = BRAND_FILE.read_text(encoding="utf-8")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1536,
        system=_system_prompt(brand_brief),
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": (
                    "Erstelle den heutigen 'Erzähl mal …'-Post exakt nach der Content-Formel "
                    "im Briefing (Hook, Alltagssituation, Wendung, eine Zeile Moral, optionaler "
                    "Kommentar-Impuls, Branding-Zeile). Waehle selbst ein Thema aus den erlaubten "
                    "Themenfeldern. Liefere zusaetzlich card_question: die Hook-Frage in Kurzform "
                    "fuer die Bildkarte."
                ),
            }
        ],
    )

    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return data


if __name__ == "__main__":
    print(json.dumps(generate_daily_content(), indent=2, ensure_ascii=False))

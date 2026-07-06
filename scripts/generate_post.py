"""Generates a social media post draft (topic, caption, hashtags) via the Anthropic API."""
import json
import os
from pathlib import Path
from typing import Optional

import anthropic

MODEL = "claude-opus-4-8"
BRAND_FILE = Path(__file__).resolve().parent.parent / "config" / "brand.md"

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


def _build_prompt(feedback: Optional[str]) -> str:
    prompt = (
        "Erstelle einen neuen Social-Media-Post-Entwurf für diese Woche. "
        "Wähle selbst ein passendes, aktuelles Thema aus den erlaubten Themenfeldern. "
        "Halte dich strikt an Tonalität und Format-Vorgaben aus dem Briefing."
    )
    if feedback:
        prompt += (
            "\n\nDer vorherige Entwurf wurde abgelehnt. Feedback dazu: "
            f"\"{feedback}\"\nBerücksichtige dieses Feedback bei der neuen Version."
        )
    return prompt


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

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_system_prompt(brand_brief),
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": _build_prompt(feedback)}],
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
        "zum Markenbriefing passen."
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

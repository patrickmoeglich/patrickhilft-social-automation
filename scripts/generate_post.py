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


def generate_post(feedback: Optional[str] = None) -> dict:
    """Returns {"topic": str, "caption": str, "hashtags": list[str]}."""
    brand_brief = BRAND_FILE.read_text(encoding="utf-8")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": (
                    "Du bist Social-Media-Manager der folgenden Marke. Halte dich exakt an "
                    "dieses Briefing:\n\n" + brand_brief
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": _build_prompt(feedback)}],
    )

    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


if __name__ == "__main__":
    print(json.dumps(generate_post(), indent=2, ensure_ascii=False))

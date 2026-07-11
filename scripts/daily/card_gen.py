"""Rendert die feste "Erzähl mal …"-Bildkarte des Kanals "Zwischen den Zeilen":
Nachtblau auf Creme, goldene Linie, Serifenschrift. Das Design ist bei jedem
Post identisch, nur die Hook-Frage wechselt - es wird kein Bildgenerierungs-
modell und kein externes Hosting-Setup (Cloudinary) benoetigt."""
import io
import os
from typing import List

from PIL import Image, ImageDraw, ImageFont

W = H = 1080
PAPER = (245, 239, 228)   # warmes Creme
INK = (44, 58, 74)        # Nachtblau
GOLD = (176, 141, 87)     # gedecktes Gold

MAX_TEXT_WIDTH = 860
MAX_LINES = 5

# Erste existierende Schrift gewinnt: gebuendelte Repo-Schrift (identisches
# Rendering ueberall), sonst macOS (lokale Tests), sonst Linux (GitHub Actions).
_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "fonts")
SERIF_BOLD_ITALIC = [
    os.path.join(_ASSETS, "serif-bold-italic.ttf"),
    "/System/Library/Fonts/Supplemental/Georgia Bold Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
]
SERIF_ITALIC = [
    os.path.join(_ASSETS, "serif-italic.ttf"),
    "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
]
SANS = [
    os.path.join(_ASSETS, "sans.ttf"),
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(candidates: List[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise RuntimeError(f"Keine der Schriften gefunden: {candidates}")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> List[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= MAX_TEXT_WIDTH:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_card(question: str) -> bytes:
    """Rendert die Karte fuer die gegebene Hook-Frage und liefert JPEG-Bytes."""
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # Frage in Zeilen umbrechen; Schrift verkleinern, bis alles passt
    size = 78
    while True:
        f_hook = _font(SERIF_BOLD_ITALIC, size)
        lines = _wrap(d, question, f_hook)
        too_wide = any(d.textlength(line, font=f_hook) > MAX_TEXT_WIDTH for line in lines)
        if len(lines) <= MAX_LINES and not too_wide:
            break
        if size <= 48:
            raise RuntimeError(f"Hook-Frage zu lang fuer die Karte: {question!r}")
        size -= 6

    f_eyebrow = _font(SANS, 34)
    f_brand = _font(SERIF_ITALIC, 42)

    def center(text: str, font: ImageFont.FreeTypeFont, y: float, fill) -> None:
        w = d.textlength(text, font=font)
        d.text(((W - w) / 2, y), text, font=font, fill=fill)

    # doppelter feiner Rahmen
    d.rectangle([36, 36, W - 36, H - 36], outline=INK, width=2)
    d.rectangle([52, 52, W - 52, H - 52], outline=GOLD, width=1)

    # Textblock vertikal zentrieren (Eyebrow + Frage + Ornament + Branding)
    line_height = int(size * 1.35)
    block = 34 + 96 + len(lines) * line_height + 100 + 50 + 52
    y = (H - block) / 2

    center(" ".join("ERZÄHL MAL …"), f_eyebrow, y, GOLD)
    y += 34 + 96
    for line in lines:
        center(line, f_hook, y, INK)
        y += line_height

    # Ornament: feine Linie mit Raute
    bx, by = W / 2, y + 100 - line_height + size  # knapp unter der letzten Zeile
    d.line([bx - 130, by, bx - 24, by], fill=GOLD, width=2)
    d.line([bx + 24, by, bx + 130, by], fill=GOLD, width=2)
    d.polygon([(bx, by - 11), (bx + 11, by), (bx, by + 11), (bx - 11, by)], fill=GOLD)

    center("Zwischen den Zeilen", f_brand, by + 50, INK)

    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


if __name__ == "__main__":
    import sys
    question = sys.argv[1] if len(sys.argv) > 1 else "Wann hast du zuletzt zu schnell geurteilt?"
    out = sys.argv[2] if len(sys.argv) > 2 else "card_preview.jpg"
    with open(out, "wb") as f:
        f.write(render_card(question))
    print("Karte gespeichert:", out)

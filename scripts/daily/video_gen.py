"""Renders a vertical (9:16) Reel/TikTok-style video from 3 still images via
ffmpeg: Ken Burns pan/zoom per image, crossfade transitions between them, and
a burned-in text overlay. No music (licensing risk with stock/AI-generated
audio) - silent video with a silent audio track for platform compatibility.

Requires the `ffmpeg` binary on PATH (preinstalled on GitHub Actions'
ubuntu-latest runners; install locally via e.g. `brew install ffmpeg`).
"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

import cloudinary_client

WIDTH = 1080
HEIGHT = 1920
FPS = 25
SEGMENT_SECONDS = 6
CROSSFADE_SECONDS = 1
FONT_PATH = os.environ.get("VIDEO_FONT_PATH", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def _escape_drawtext(text: str) -> str:
    # ffmpeg drawtext treats \ : ' as special characters inside the filter string.
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
    return text


def _run(cmd: List[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg-Befehl fehlgeschlagen: {' '.join(cmd)}\n{result.stdout[-3000:]}")


def _render_segment(image_path: Path, out_path: Path) -> None:
    frames = SEGMENT_SECONDS * FPS
    zoompan = (
        f"scale={WIDTH * 2}:{HEIGHT * 2}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='min(zoom+0.0012,1.15)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )
    _run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
            "-vf", zoompan,
            "-t", str(SEGMENT_SECONDS),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(out_path),
        ]
    )


def render_video(image_paths: List[Path], overlay_text: str, out_path: Path) -> None:
    """Renders the final vertical video with crossfades + text overlay + silent audio."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        segment_paths = []
        for i, image_path in enumerate(image_paths):
            segment_path = tmp_dir / f"segment_{i}.mp4"
            _render_segment(image_path, segment_path)
            segment_paths.append(segment_path)

        inputs = []
        for segment_path in segment_paths:
            inputs += ["-i", str(segment_path)]

        filter_parts = []
        prev_label = "0:v"
        offset = SEGMENT_SECONDS - CROSSFADE_SECONDS
        for i in range(1, len(segment_paths)):
            out_label = f"v{i}" if i < len(segment_paths) - 1 else "vfade"
            filter_parts.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:duration={CROSSFADE_SECONDS}:offset={offset}[{out_label}]"
            )
            prev_label = out_label
            offset += SEGMENT_SECONDS - CROSSFADE_SECONDS

        escaped_text = _escape_drawtext(overlay_text)
        drawtext = (
            f"drawtext=fontfile={FONT_PATH}:text='{escaped_text}':"
            "fontsize=64:fontcolor=white:borderw=3:bordercolor=black@0.8:"
            "x=(w-text_w)/2:y=h-th-180"
        )
        filter_parts.append(f"[{prev_label}]{drawtext}[vout]")

        filter_complex = ";".join(filter_parts)

        _run(
            [
                "ffmpeg", "-y",
                *inputs,
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", f"{len(segment_paths)}:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest",
                str(out_path),
            ]
        )


def generate_and_host_video(image_bytes_list: List[bytes], overlay_text: str) -> dict:
    """Renders the vertical video from raw image bytes and uploads it to Cloudinary.

    Returns {"bytes": raw mp4 bytes, "url": public Cloudinary URL} - the raw bytes
    are kept around for publishers that require a direct binary upload (LinkedIn, X)
    instead of a public URL (Instagram, TikTok).
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        image_paths = []
        for i, image_bytes in enumerate(image_bytes_list):
            image_path = tmp_dir / f"image_{i}.png"
            image_path.write_bytes(image_bytes)
            image_paths.append(image_path)

        out_path = tmp_dir / "daily_reel.mp4"
        render_video(image_paths, overlay_text, out_path)
        video_bytes = out_path.read_bytes()
        url = cloudinary_client.upload(video_bytes, resource_type="video", filename="daily_reel.mp4")
        return {"bytes": video_bytes, "url": url}

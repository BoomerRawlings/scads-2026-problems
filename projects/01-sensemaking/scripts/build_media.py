"""Rebuild the tiny synthetic visual fixtures; requires Pillow and ffmpeg.

These are caption boards, not recordings of real events. They are derived from
the authored annotation/transcript and are not independent corroboration.
"""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def board(title, message, stamp):
    image = Image.new("RGB", (1280, 720), "#eef2eb")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=34)
    small = ImageFont.load_default(size=23)
    large = ImageFont.load_default(size=54)
    draw.rectangle((0, 0, 1280, 118), fill="#18362d")
    draw.text((55, 38), "CBRI / RIVERWATCH", font=large, fill="white")
    draw.text((55, 160), title, font=font, fill="#18362d")
    y = 245
    for line in textwrap.wrap(message, width=56):
        draw.text((55, y), line, font=font, fill="#203d32")
        y += 52
    draw.rectangle((0, 605, 1280, 720), fill="#dce6d7")
    draw.text((55, 628), stamp, font=small, fill="#18362d")
    draw.text((55, 665), "SYNTHETIC FIXTURE / Caption board / No real event", font=small, fill="#18362d")
    return image


def main():
    binary = shutil.which("ffmpeg")
    if not binary:
        raise SystemExit("Install ffmpeg to regenerate video")
    media = DATA / "media"
    media.mkdir(exist_ok=True)
    board("Planning board: DELAYED", "Riverwatch - delayed. Field release blocked pending sensor acceptance.", "2026-09-05 / Authored board fixture").save(media / "riverwatch-board.png")
    captions = [
        "Riverwatch readiness is delayed. Keep field release on hold until the Silt Sensor Batch passes acceptance.",
        "The register still says ready. Show that dated entry next to the dependency review when preparing the status report.",
        "Scope the concern to Riverwatch deployment. We have not established that other institute activities are delayed.",
    ]
    with tempfile.TemporaryDirectory() as directory:
        for second in range(30):
            index = 0 if second < 14 else 1 if second < 27 else 2
            board("Coordination review / caption-only video", captions[index], f"2026-09-05 / Video frame 00:{second:02d} / No audio").save(Path(directory) / f"frame-{second:03d}.png")
        subprocess.run([binary, "-v", "error", "-y", "-framerate", "1", "-i", str(Path(directory) / "frame-%03d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "1", str(media / "riverwatch-review.mp4")], check=True)
    manifest_path = DATA / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in manifest:
        if record["id"] in {"img-note-001", "video-tx-001"}:
            record["media_path"] = "media/riverwatch-board.png" if record["id"] == "img-note-001" else "media/riverwatch-review.mp4"
            record["media_provenance"] = "Synthetic caption media rendered from authored fixture text; not independent corroboration. No recorded people or audio."
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Created source PNG, 30-second caption-only MP4, and manifest links")


if __name__ == "__main__":
    main()

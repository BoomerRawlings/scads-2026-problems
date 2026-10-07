"""Return source pixels to the host model; never substitute an annotation for media."""

import base64
import hashlib
from io import BytesIO
import json
import math
import mimetypes
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image


def file_sha256(path: Path) -> str:
    """Hash source bytes without loading the whole file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _video_duration(path: Path) -> float | None:
    binary = shutil.which("ffprobe")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=20, check=False,
        )
        duration = float(json.loads(result.stdout)["format"]["duration"])
        if result.returncode or not math.isfinite(duration) or duration <= 0:
            return None
        return duration
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return None


def _sample_timestamps(duration: float | None) -> list[float]:
    if duration is None:
        return [0.0]
    # Stay before EOF. Three samples bound decoding cost; they never imply full coverage.
    last = min(duration - min(1.0, duration / 10), 3600.0)
    return sorted({0.0, round(last / 2, 3), round(last, 3)})


def inspect_media(workspace, evidence_id: str) -> dict:
    """Describe available bytes, provenance, and duration-derived video samples."""
    evidence = workspace.read(evidence_id)
    relative = evidence.get("media_path")
    result = {
        "evidence_id": evidence_id, "kind": evidence["kind"],
        "source": evidence["source"], "extraction": evidence.get("extraction"),
        "media_path": relative, "available": False, "mime_type": None,
        "size_bytes": None, "media_sha256": None,
        "provenance": evidence.get("media_provenance", "See dataset provenance"),
        "duration_seconds": None, "suggested_timestamps": [],
    }
    if not relative:
        result["note"] = "No local source media attached; extraction only."
        return result
    path = workspace._safe_path(relative)
    result["mime_type"] = mimetypes.guess_type(path.name)[0]
    result["available"] = path.is_file()
    if not result["available"]:
        result["note"] = "Indexed source media is missing from this dataset."
        return result
    result["size_bytes"] = path.stat().st_size
    result["media_sha256"] = file_sha256(path)
    if path.suffix.lower() == ".mp4":
        duration = _video_duration(path)
        result["duration_seconds"] = duration
        result["suggested_timestamps"] = _sample_timestamps(duration)
        result["note"] = (
            "Duration from ffprobe. Suggested samples do not establish unseen frames or audio."
            if duration is not None else
            "Duration unavailable; install ffprobe or check source. Default samples only the first frame."
        )
    return result


def _image_block(raw: bytes) -> dict:
    with Image.open(BytesIO(raw)) as image:
        image.thumbnail((1280, 1280))
        image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
    return {"type": "image", "mimeType": "image/png", "data": base64.b64encode(buffer.getvalue()).decode("ascii")}


def _decoded_timestamp(stderr: bytes) -> dict:
    """Read the first emitted frame PTS, not the requested seek offset."""
    log = stderr.decode("utf-8", errors="replace")
    base = re.search(r"\bconfig in time_base:\s*(\d+)/(\d+)", log)
    frame = re.search(r"\bn:\s*0\s+pts:\s*(-?\d+)\s+pts_time:", log)
    if not base or not frame or int(base[2]) == 0:
        raise ValueError("Decoded frame has no usable source presentation timestamp")
    ticks, numerator, denominator = int(frame[1]), int(base[1]), int(base[2])
    seconds = ticks * numerator / denominator
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Decoded frame source timestamp is outside supported nonnegative locators")
    return {"source_pts": ticks, "source_time_base": f"{numerator}/{denominator}",
            "source_timestamp_seconds": round(seconds, 6)}


def read_media(workspace, evidence_id: str, timestamps: list[float] | None = None) -> list[dict]:
    evidence = workspace.read(evidence_id)
    relative = evidence.get("media_path")
    if not relative:
        raise ValueError("No raw media attached to this evidence. An annotation is not a source image/video.")
    path = workspace._safe_path(relative)
    if not path.is_file():
        raise ValueError("Attached media does not exist")
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Prototype media limit is 25 MiB")
    header = {"evidence_id": evidence_id, "media_path": relative, "media_sha256": file_sha256(path), "provenance": evidence.get("media_provenance", "See dataset provenance"), "note": "Interpret these pixels directly. Indexed assertions are source metadata and may disagree. Sampled frames do not establish the contents of the entire video."}
    blocks = [{"type": "text", "text": json.dumps(header)}]
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        blocks.append(_image_block(path.read_bytes()))
        return blocks
    if path.suffix.lower() != ".mp4":
        raise ValueError("Supported source formats: PNG, JPEG, WebP, MP4")
    binary = shutil.which("ffmpeg")
    if not binary:
        raise ValueError("ffmpeg is required for MP4 frame inspection")
    if timestamps is not None and (not timestamps or len(timestamps) > 4 or any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 <= t <= 3600 for t in timestamps)):
        raise ValueError("Provide 1-4 finite timestamps between 0 and 3600 seconds")
    if timestamps is None:
        duration = _video_duration(path)
        timestamps = _sample_timestamps(duration)
        header["duration_seconds"] = duration
        header["sample_selection"] = "duration-derived" if duration is not None else "first-frame fallback; duration unavailable"
    header["samples"] = []
    for seconds in timestamps:
        # Input seeking remains bounded. copyts preserves source PTS; passthrough
        # prevents output synchronization from duplicating/re-timestamping frames.
        result = subprocess.run([binary, "-hide_banner", "-v", "info", "-copyts",
                                 "-ss", str(seconds), "-i", str(path), "-map", "0:v:0",
                                 "-frames:v", "1", "-vf", "showinfo", "-fps_mode", "passthrough",
                                 "-an", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
                                capture_output=True, timeout=20, check=False)
        if result.returncode or not result.stdout:
            raise ValueError(f"Could not decode video frame at {seconds}s")
        sample = {"requested_seek_seconds": seconds, **_decoded_timestamp(result.stderr)}
        header["samples"].append(sample)
        actual = sample["source_timestamp_seconds"]
        blocks.append({"type": "text", "text": f"Evidence {evidence_id}; sampled source frame at {actual:.6f} seconds (source PTS, rounded to microseconds); requested seek offset {seconds:.3f} seconds; no audio processing."})
        blocks.append(_image_block(result.stdout))
    blocks[0]["text"] = json.dumps(header)
    return blocks

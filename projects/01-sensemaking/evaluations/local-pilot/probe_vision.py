"""Development probe: pixels without annotation; use documented 64/256 server budget.

The image-token settings below record the operator's declared server launch;
this script does not discover or enforce those server flags.
"""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import local_agent
import media_tools
from sensemaking import Workspace

project = Path(__file__).resolve().parents[2]
model = local_agent.LocalModel("http://127.0.0.1:18571/v1")
model.identify(30)
workspace = Workspace(project / "data")
blocks = media_tools.read_media(workspace, "img-note-001")
pixels = next(block for block in blocks if block["type"] == "image")
prompt = "Transcribe the visible text exactly. Omit anything you cannot read. Return plain text, at most 180 words."
started = time.monotonic()
result = model.request("/chat/completions", {
    "model": model.model, "temperature": 0, "seed": 0, "max_tokens": 512,
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:" + pixels["mimeType"] + ";base64," + pixels["data"]}},
    ]}],
}, 600)
record = {"purpose": "Development-only direct-pixel transcription probe; not an agent workflow or accuracy benchmark",
          "model": model.metadata, "prompt": prompt, "image_min_tokens": 64, "image_max_tokens": 256,
          "source": "data/media/riverwatch-board.png",
          "source_sha256": media_tools.file_sha256(project / "data/media/riverwatch-board.png"),
          "elapsed_seconds": round(time.monotonic() - started, 3),
          "text": result["choices"][0]["message"]["content"],
          "finish_reason": result["choices"][0].get("finish_reason")}
output = project / "runs" / "vision-probe-256.json"
output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
workspace.close()

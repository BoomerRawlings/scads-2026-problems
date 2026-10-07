"""Private extraction workspace registry, separate from the discovery catalog."""
from __future__ import annotations
import json
import hashlib
import re
from pathlib import Path
from .io import read_json, write_json
from .schema import identifier, require
from .review import ReviewStore


class Workspace:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.reviews = ReviewStore(self.path / "reviews.sqlite3")

    def record_path(self, doc_id):
        identifier(doc_id, "doc_id")
        return self.path / "records" / f"{doc_id}.json"

    def record(self, doc_id):
        return read_json(self.record_path(doc_id))

    def records(self):
        return [read_json(path) for path in sorted((self.path / "records").glob("*.json"))]

    def ingest_manifest(self, manifest, force_ocr=False, max_pages=None, resume=True, *, page_timeout_seconds=120.0):
        from .ingest import ingest_pdf
        manifest = Path(manifest).resolve()
        if manifest.suffix.lower() == ".jsonl":
            entries = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:
            entries = read_json(manifest)
            if isinstance(entries, dict):
                entries = entries.get("documents", [entries])
        summaries = []
        seen = set()
        for entry in entries:
            if entry.get("admission_status", entry.get("status", "admitted")) != "admitted":
                continue
            doc = entry.get("document") or {key: entry[key] for key in ("doc_id", "title", "manufacturer", "models", "model_categories", "category", "language", "revision", "source_uri", "rights") if key in entry}
            identifier(doc["doc_id"], "doc_id")
            require(doc["doc_id"] not in seen, "Duplicate document ID in manifest")
            seen.add(doc["doc_id"])
            source = Path(entry["path"])
            if not source.is_absolute():
                root = manifest.parent
                # Project-relative paths are declared by an optional manifest base; otherwise relative to manifest.
                source = (root / entry.get("base", ".") / source).resolve()
            require(source.is_file(), f"Missing source: {source}")
            if "byte_size" in entry:
                require(source.stat().st_size == entry["byte_size"], f"Source size mismatch: {doc['doc_id']}")
            expected = entry.get("sha256")
            if "sha256" in entry:
                require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "Invalid manifest SHA-256 pin")
                with source.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                require(actual == expected, f"Source hash mismatch: {doc['doc_id']}")
            record = ingest_pdf(source, doc, self.path / "processing" / doc["doc_id"], force_ocr=force_ocr,
                resume=resume, max_pages=max_pages, page_timeout_seconds=page_timeout_seconds)
            record["source_path"] = str(source)
            write_json(self.record_path(doc["doc_id"]), record)
            summaries.append({"doc_id": doc["doc_id"], "pages": len(record["pages"]), "assertions": len(record["assertions"]), "status": record.get("processing_status", "unknown")})
        return summaries

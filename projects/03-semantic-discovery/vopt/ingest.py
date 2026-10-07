"""Offline PDF ingestion with durable, source/configuration-addressed checkpoints.

Page coordinates are in points in the *displayed* (rotated) page, matching the
image returned by PyMuPDF's default ``get_pixmap``. No OCR code is allowed to
choose its own asset path or retrieve weights from the network.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import copy
import time
from contextlib import ExitStack, contextmanager
from typing import Any
from .extraction_worker import DEFAULT_PAGE_TIMEOUT_SECONDS, MAX_RESULT_BYTES, PageProcess, validate_execution

INGEST_VERSION = "vopt-ingest-2"
RENDER_DPI = 200
MAX_RENDER_PIXELS = 24_000_000
MAX_PAGE_ATTEMPTS = 3
_OCR: dict[str, Any] = {}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _source_snapshot(source: Path, expected_hash: str):
    """Read only hash-verified private bytes, including after worker restarts.

    A final original-file hash check alone cannot protect interrupted checkpoints
    if an external editor changes and later restores the original file.
    """
    temporary = tempfile.TemporaryDirectory(prefix="vopt-source-snapshot-")
    try:
        target = Path(temporary.name) / "source.pdf"
        digest = hashlib.sha256()
        with source.open("rb") as original, target.open("wb") as snapshot:
            for chunk in iter(lambda: original.read(1024 * 1024), b""):
                digest.update(chunk)
                snapshot.write(chunk)
        if digest.hexdigest() != expected_hash:
            raise ValueError("Source changed while making verified PDF snapshot; retry from stable bytes")
        yield target
    finally:
        # Windows can finish releasing mapped-file handles just after a forced
        # child exit. Retry cleanup briefly; never leave a silent private copy.
        for attempt in range(21):
            try:
                temporary.cleanup()
                break
            except PermissionError:
                if attempt == 20:
                    raise
                time.sleep(.05)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".checkpoint-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            payload = dict(value)
            payload.pop("checkpoint_integrity", None)
            payload["checkpoint_integrity"] = hashlib.sha256(_canonical(payload)).hexdigest()
            stream.write(_canonical(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _distribution_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "missing"


def local_ocr_assets() -> dict[str, str]:
    """Resolve only weights shipped in the installed RapidOCR distribution.

    Missing or nonunique assets fail locally before RapidOCR is constructed.
    This also supports a preflight command without loading ONNX runtimes.
    """
    spec = importlib.util.find_spec("rapidocr_onnxruntime")
    if not spec or not spec.origin:
        raise RuntimeError("Offline OCR unavailable: install the packaged rapidocr-onnxruntime wheel and its local weights.")
    directory = Path(spec.origin).parent / "models"
    result = {}
    for role in ("det", "cls", "rec"):
        paths = sorted(directory.glob(f"*_{role}*.onnx"))
        if len(paths) != 1 or not paths[0].is_file() or paths[0].stat().st_size < 1024:
            raise RuntimeError(f"Offline OCR asset missing or ambiguous: {role} model in packaged models directory. No download attempted.")
        result[role] = str(paths[0])
    return result


def processing_signature() -> dict:
    """Fingerprint code, configuration, native/OCR versions and actual weights."""
    modules = [Path(__file__), Path(__file__).with_name("extract.py"), Path(__file__).with_name("extraction_worker.py")]
    signature = {
        "version": INGEST_VERSION,
        "code": {path.name: _file_hash(path) for path in modules if path.exists()},
        "pymupdf": _distribution_version("PyMuPDF"),
        "rapidocr": _distribution_version("rapidocr-onnxruntime"),
        "onnxruntime": _distribution_version("onnxruntime"),
        "render_dpi": RENDER_DPI,
        "max_render_pixels": MAX_RENDER_PIXELS,
        "max_page_attempts": MAX_PAGE_ATTEMPTS,
        "ocr_orientation_retry": [90, 270],
        "ocr_threads": 2,
        "execution": {"mode": "subprocess", "page_timeout_seconds": DEFAULT_PAGE_TIMEOUT_SECONDS,
                      "max_result_bytes": MAX_RESULT_BYTES, "python_network_blocked_in_worker": True},
    }
    try:
        signature["assets"] = {role: _file_hash(Path(path)) for role, path in local_ocr_assets().items()}
    except RuntimeError as exc:
        signature["assets"] = {"error": str(exc)}
    return signature


def _page_signature(signature: dict) -> dict:
    result = dict(signature)
    result["code"] = {name: digest for name, digest in signature.get("code", {}).items() if name != "extract.py"}
    return result


def _ocr_engine():
    assets = local_ocr_assets()
    key = hashlib.sha256(_canonical({role: _file_hash(Path(path)) for role, path in assets.items()})).hexdigest()
    if key not in _OCR:
        # Import happens only after explicit local weights have been verified.
        from rapidocr_onnxruntime import RapidOCR

        _OCR[key] = RapidOCR(
            det_model_path=assets["det"], cls_model_path=assets["cls"], rec_model_path=assets["rec"],
            intra_op_num_threads=2, inter_op_num_threads=2,
            print_verbose=False,
        )
    return _OCR[key]


def _native_lines(page) -> list[dict]:
    """Preserve word geometry and split line spans separated by table gutters."""
    import pymupdf as fitz

    word_groups: dict[tuple[int, int], list] = {}
    for word in page.get_text("words", sort=True):
        if str(word[4]).strip():
            word_groups.setdefault((word[5], word[6]), []).append(word)
    lines = []
    for words in word_groups.values():
        words.sort(key=lambda word: word[0])
        chunks: list[list] = []
        for word in words:
            if chunks and word[0] - chunks[-1][-1][2] <= max(12, (word[3] - word[1]) * 1.4):
                chunks[-1].append(word)
            else:
                chunks.append([word])
        for chunk in chunks:
            transformed = []
            for word in chunk:
                rectangle = fitz.Rect(word[:4]) * page.rotation_matrix
                transformed.append({"text": word[4], "bbox": [round(value, 3) for value in rectangle],
                                    "reading_bbox": [round(value, 3) for value in word[:4]]})
            bbox = [min(item["bbox"][0] for item in transformed), min(item["bbox"][1] for item in transformed),
                    max(item["bbox"][2] for item in transformed), max(item["bbox"][3] for item in transformed)]
            reading = [min(word[0] for word in chunk), min(word[1] for word in chunk), max(word[2] for word in chunk), max(word[3] for word in chunk)]
            lines.append({"text": " ".join(word[4] for word in chunk), "bbox": bbox, "reading_bbox": reading, "words": transformed})
    return sorted(lines, key=lambda item: (item["bbox"][1], item["bbox"][0]))


def _render_array(page):
    import pymupdf as fitz
    import numpy as np

    scale = RENDER_DPI / 72
    estimated = page.rect.width * page.rect.height * scale * scale
    if estimated > MAX_RENDER_PIXELS:
        scale *= math.sqrt(MAX_RENDER_PIXELS / estimated)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
    array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
    return array


def _ocr_quality(result) -> float:
    if not result:
        return 0.0
    characters = sum(sum(character.isalnum() for character in str(item[1])) for item in result)
    if not characters:
        return 0.0
    mean = sum(float(item[2]) * max(1, len(str(item[1]))) for item in result) / sum(max(1, len(str(item[1]))) for item in result)
    return mean * min(1.0, characters / 35)


def _ocr_lines(page) -> list[dict]:
    import numpy as np

    pixels = _render_array(page)
    # Truly empty pages are successfully observed empty, not OCR failures.
    if float(np.mean(np.min(pixels, axis=2) < 235)) < 0.00002:
        return []
    engine = _ocr_engine()
    result, _ = engine(pixels, use_cls=True)
    turns = 0
    if _ocr_quality(result) < 0.78:
        best = _ocr_quality(result)
        for rotation in (1, 3):
            candidate, _ = engine(np.ascontiguousarray(np.rot90(pixels, rotation)), use_cls=True)
            quality = _ocr_quality(candidate)
            if quality > best:
                best, result, turns = quality, candidate, rotation
    if not result:
        raise RuntimeError("OCR detected no readable text on a nonblank page; coverage remains unknown.")
    height, width = pixels.shape[:2]
    lines = []
    for polygon, text, score in result:
        if not str(text).strip():
            continue
        points = []
        for x, y in polygon:
            if turns == 1:
                x, y = width - y, x
            elif turns == 3:
                x, y = y, height - x
            points.append((float(x) / width * page.rect.width, float(y) / height * page.rect.height))
        bbox = [max(0.0, min(point[0] for point in points)), max(0.0, min(point[1] for point in points)),
                min(page.rect.width, max(point[0] for point in points)), min(page.rect.height, max(point[1] for point in points))]
        reading = [min(float(point[0]) for point in polygon) / width * page.rect.width,
                   min(float(point[1]) for point in polygon) / height * page.rect.height,
                   max(float(point[0]) for point in polygon) / width * page.rect.width,
                   max(float(point[1]) for point in polygon) / height * page.rect.height]
        lines.append({"text": str(text).strip(), "bbox": [round(value, 3) for value in bbox], "reading_bbox": reading, "confidence": round(float(score), 4)})
    if not lines:
        raise RuntimeError("OCR returned no readable lines on a nonblank page.")
    return sorted(lines, key=lambda item: (item["bbox"][1], item["bbox"][0]))


def _read_page(page, force_ocr: bool) -> dict:
    import pymupdf

    pymupdf.TOOLS.mupdf_warnings(reset=True)
    native = _native_lines(page)
    text = "\n".join(line["text"] for line in native)
    usable = sum(character.isalnum() for character in text) >= 12 and "\ufffd" not in text
    area = max(1, page.rect.width * page.rect.height)
    # Image-heavy mixed pages need OCR even if a searchable running header exists.
    image_area = sum(max(0, info["bbox"][2] - info["bbox"][0]) * max(0, info["bbox"][3] - info["bbox"][1])
                     for info in page.get_image_info())
    use_native = usable and not force_ocr and (image_area / area < 0.10 or sum(character.isalnum() for character in text) >= 180)
    if use_native:
        lines, engine = native, "pymupdf-text"
    elif not force_ocr and not native and not page.get_images() and not page.get_drawings():
        lines, engine = [], "pymupdf-empty"
    else:
        lines, engine = _ocr_lines(page), "rapidocr-onnx"
    decoder_warnings = pymupdf.TOOLS.mupdf_warnings(reset=True)
    if decoder_warnings and any(marker in decoder_warnings.lower() for marker in ("format error", "invalid code", "cannot decode", "truncated", "premature end")):
        raise RuntimeError("PDF decoder could not establish full page coverage: " + decoder_warnings[:400])
    result = {"page_number": page.number + 1, "width": page.rect.width, "height": page.rect.height,
            "status": "ok", "engine": engine, "text": "\n".join(line["text"] for line in lines),
            "lines": lines, "error": None}
    if decoder_warnings:
        result["warnings"] = [decoder_warnings[:500]]
    return result


def _refresh_status(record: dict) -> None:
    successful = sum(page["status"] == "ok" for page in record["pages"])
    total = len(record["pages"])
    record["coverage"] = {"total_pages": total, "successful_pages": successful, "failed_pages": total - successful,
                          "fraction": successful / total if total else 0.0}
    record["processing_status"] = "complete" if total and successful == total else "partial" if total else "rejected"


class _DirectPages:
    """Explicit diagnostic mode; native calls are not isolated or time bounded."""

    def __init__(self, path):
        import pymupdf
        self.pdf = pymupdf.open(path)
        try:
            if self.pdf.needs_pass:
                raise ValueError("Encrypted PDF requires an unlocked local copy.")
            if not self.pdf.is_pdf or self.pdf.page_count == 0:
                raise ValueError("Input must be a nonempty PDF.")
            self.page_count = self.pdf.page_count
        except BaseException:
            self.pdf.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.pdf.close()

    def read_page(self, index, force_ocr):
        return _read_page(self.pdf.load_page(index), force_ocr)


def _open_pages(path, isolate_pages, page_timeout_seconds):
    if isolate_pages:
        return PageProcess(path, page_timeout_seconds).__enter__()
    return _DirectPages(path)


def _execution_signature(signature, isolate_pages, page_timeout_seconds):
    signature["execution"] = {"mode": "subprocess" if isolate_pages else "in_process",
                              "page_timeout_seconds": float(page_timeout_seconds) if isolate_pages else None,
                              "max_result_bytes": MAX_RESULT_BYTES if isolate_pages else None,
                              "python_network_blocked_in_worker": bool(isolate_pages)}
    return signature


def ingest_pdf(path, document, output_dir, force_ocr=False, resume=True, max_pages=None, *,
               isolate_pages=True, page_timeout_seconds=DEFAULT_PAGE_TIMEOUT_SECONDS) -> dict:
    """Read a PDF locally and checkpoint each page before proceeding.

    Resume reuses validated successful pages and retries failures at most three
    times per cache identity. ``resume=False`` explicitly resets that budget and
    reprocesses everything. ``max_pages`` is a work bound, never truncates the
    coverage denominator, and may be increased on a subsequent resumed call.
    Page-cache identity includes document ID, source bytes, ingestion code,
    engine versions, OCR weight hashes and processing configuration. Metadata
    corrections and extractor changes reuse observed pages but rebuild the full
    private record and its processing version, invalidating bound approvals.
    Native opening and each page run in one persistent subprocess by default.
    A timeout/crash kills and reaps it; the next page starts a fresh worker. OCR
    models are reused across successful pages. ``isolate_pages=False`` is an
    explicit diagnostic opt-out without hard timeout or worker network guard.
    """
    from .extract import extract_assertions, extraction_signature

    validate_execution(isolate_pages, page_timeout_seconds)
    path = Path(path)
    if not isinstance(document, dict) or not isinstance(document.get("doc_id"), str) or not document["doc_id"].strip():
        raise ValueError("document.doc_id is required for stable source identity")
    if max_pages is not None and (isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1):
        raise ValueError("max_pages must be a positive integer or None")
    source_hash = _file_hash(path)
    signature = _execution_signature(processing_signature(), isolate_pages, page_timeout_seconds)
    page_signature = _page_signature(signature)
    identity = {"sha256": source_hash, "doc_id": document["doc_id"], "signature": page_signature, "force_ocr": bool(force_ocr)}
    cache_key = hashlib.sha256(_canonical(identity)).hexdigest()
    cache_path = Path(output_dir) / "cache" / cache_key / "record.json"
    record = {"schema_version": 1, "document": json.loads(_canonical(document)), "sha256": source_hash,
              "page_processing_version": INGEST_VERSION + ":" + hashlib.sha256(_canonical(page_signature)).hexdigest()[:20],
              "extraction_version": extraction_signature(),
              "cache_key": cache_key, "pages": [], "assertions": [], "warnings": [], "execution": signature["execution"]}
    record["processing_version"] = record["page_processing_version"] + "+" + record["extraction_version"]
    if not document.get("models"):
        record["warnings"].append("identity_required: supply verified product model identities before technical extraction.")
    resources = ExitStack()
    try:
        snapshot = resources.enter_context(_source_snapshot(path, source_hash))
        reader = resources.enter_context(_open_pages(snapshot, isolate_pages, page_timeout_seconds))
    except Exception as exc:
        resources.close()
        record["errors"] = [f"{type(exc).__name__}: {exc}"]
        _refresh_status(record)
        if resume and cache_path.exists():
            record["warnings"].append("Existing page checkpoint retained after source-open failure; retry from the same stable bytes.")
        else:
            _atomic_json(cache_path, record)
        return record
    except BaseException:
        resources.close()
        raise
    with resources:
        record["pages"] = [{"page_number": number + 1, "width": None, "height": None, "status": "failed",
                            "engine": None, "text": "", "lines": [], "error": "not_processed", "attempts": 0}
                           for number in range(reader.page_count)]
        if resume and cache_path.exists():
            try:
                saved = json.loads(cache_path.read_text("utf-8"))
                integrity = saved.pop("checkpoint_integrity", None)
                if integrity != hashlib.sha256(_canonical(saved)).hexdigest():
                    raise ValueError("Checkpoint integrity mismatch")
                if (saved.get("cache_key") == cache_key and saved.get("sha256") == source_hash
                        and saved.get("document", {}).get("doc_id") == document["doc_id"]
                        and saved.get("processing_status") != "rejected"):
                    for old_page in saved.get("pages", []):
                        number = old_page.get("page_number")
                        if isinstance(number, int) and 1 <= number <= reader.page_count and _valid_cached_page(old_page):
                            record["pages"][number - 1] = old_page
            except (OSError, ValueError, TypeError, AttributeError):
                record["warnings"].append("Invalid cache ignored; pages reprocessed from the source.")
        _refresh_status(record)
        _atomic_json(cache_path, record)
        for index in range(reader.page_count):
            previous = record["pages"][index]
            if previous["status"] == "ok":
                continue
            if max_pages is not None and index >= max_pages:
                if previous.get("attempts", 0) == 0:
                    previous["error"] = "page_limit: not processed; metadata coverage unknown"
                continue
            attempts = previous.get("attempts", 0)
            if attempts >= MAX_PAGE_ATTEMPTS:
                continue
            try:
                result = reader.read_page(index, bool(force_ocr))
                result["attempts"] = attempts + 1
                record["pages"][index] = result
            except KeyboardInterrupt:
                previous["error"] = "interrupted: page not completed; metadata coverage unknown"
                _refresh_status(record)
                _atomic_json(cache_path, record)
                raise
            except Exception as exc:
                previous.update(status="failed", engine=None, text="", lines=[], attempts=attempts + 1,
                                error=f"{type(exc).__name__}: {exc}")
                if isolate_pages:
                    previous["worker_network_attempts"] = getattr(exc, "network_attempts", None)
            _refresh_status(record)
            _atomic_json(cache_path, record)
        if _file_hash(path) != source_hash:
            record["assertions"] = []
            record["errors"] = ["Source changed during ingestion; retry from a stable local file."]
            for page in record["pages"]:
                page.update(status="failed", engine=None, text="", lines=[], width=None, height=None, attempts=0,
                            error="source_changed: page evidence invalidated; metadata coverage unknown")
            _refresh_status(record)
            record["processing_status"] = "rejected"
            _atomic_json(cache_path, record)
            return record
        record["assertions"] = extract_assertions(record["pages"], record["document"])
        _refresh_status(record)
        _atomic_json(cache_path, record)
        return record


def _valid_cached_page(page: dict) -> bool:
    if page.get("status") not in {"ok", "failed"} or not isinstance(page.get("text"), str) or not isinstance(page.get("lines"), list):
        return False
    attempts = page.get("attempts", 0)
    if not isinstance(attempts, int) or attempts < 0 or attempts > MAX_PAGE_ATTEMPTS:
        return False
    if page["status"] == "ok":
        if page.get("error") is not None or not page.get("engine"):
            return False
        for line in page["lines"]:
            if not isinstance(line, dict) or not isinstance(line.get("text"), str):
                return False
            box = line.get("bbox")
            if not isinstance(box, list) or len(box) != 4 or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in box):
                return False
    return True


def reocr_pages(path, record: dict, page_numbers: list[int], *, isolate_pages=True,
                page_timeout_seconds=DEFAULT_PAGE_TIMEOUT_SECONDS) -> dict:
    """Explicit targeted raster reprocessing, preserving source identity.

    Useful when embedded OCR corrupted identifiers. No fuzzy ID substitution.
    The caller persists this new record atomically and old approvals become stale.
    """
    from .extract import reextract_record

    validate_execution(isolate_pages, page_timeout_seconds)
    if not page_numbers or any(type(number) is not int or number < 1 or number > len(record.get("pages", [])) for number in page_numbers):
        raise ValueError("page_numbers must contain existing one-based page numbers")
    source = Path(path)
    if _file_hash(source) != record.get("sha256"):
        raise ValueError("Source hash changed; run full ingestion before targeted OCR")
    result = copy.deepcopy(record)
    signature = _page_signature(_execution_signature(processing_signature(), isolate_pages, page_timeout_seconds))
    page_version = INGEST_VERSION + ":" + hashlib.sha256(_canonical(signature)).hexdigest()[:20]
    changes = []
    with _source_snapshot(source, record["sha256"]) as snapshot, _open_pages(snapshot, isolate_pages, page_timeout_seconds) as reader:
        if reader.page_count != len(result["pages"]):
            raise ValueError("Source page identity or encryption does not match record")
        for number in sorted(set(page_numbers)):
            old = result["pages"][number - 1]
            try:
                replacement = reader.read_page(number - 1, True)
            except Exception as exc:
                replacement = dict(old, status="failed", engine=None, text="", lines=[], error=f"{type(exc).__name__}: {exc}")
                if isolate_pages:
                    replacement["worker_network_attempts"] = getattr(exc, "network_attempts", None)
            replacement["attempts"] = old.get("attempts", 0) + 1
            replacement["processing_version"] = page_version
            result["pages"][number - 1] = replacement
            changes.append({"page": number, "old_page_sha256": hashlib.sha256(_canonical(old)).hexdigest(),
                            "old_engine": old.get("engine"), "new_engine": replacement.get("engine"), "processing_version": page_version})
    result.setdefault("page_refreshes", []).extend(changes)
    if _file_hash(source) != record["sha256"]:
        raise ValueError("Source changed during targeted OCR; discard results and retry from stable bytes")
    result["page_processing_version"] = result.get("page_processing_version", result["processing_version"]) + "+targeted-ocr:" + hashlib.sha256(_canonical(changes)).hexdigest()[:16]
    _refresh_status(result)
    return reextract_record(result)

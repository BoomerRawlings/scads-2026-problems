"""Reproducible *development* diagnostics on source-inspected authentic scans.

No human labels, held-out accuracy or exhaustive precision/recall is claimed.
Run from the project root with the installed local environment:
    python scripts/evaluate_extraction.py
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vopt.extract import extract_assertions, reextract_record
from vopt.ingest import _read_page, processing_signature
from vopt.io import digest, read_json, write_json
from vopt.review import record_fingerprint
from vopt.workspace import Workspace


@contextmanager
def python_network_blocked():
    original_connect, original_create = socket.socket.connect, socket.create_connection
    def blocked(*args, **kwargs):
        raise RuntimeError("Offline evaluation blocked a Python network connection")
    socket.socket.connect = blocked
    socket.create_connection = blocked
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection = original_connect, original_create


def matches(candidate, lead):
    for key in ("model", "attribute", "unit", "qualifier"):
        if candidate.get(key) != lead.get(key):
            return False
    for key in ("value", "value_max"):
        expected, actual = lead.get(key), candidate.get(key)
        if expected is None:
            if actual is not None:
                return False
        elif type(actual) not in (int, float) or abs(actual - expected) > max(.000001, abs(expected) * .000001):
            return False
    return candidate.get("evidence", {}).get("page") == lead["pdf_page"]


def lead_diagnostics(candidates, leads):
    output = []
    for lead in leads:
        found = [candidate for candidate in candidates if candidate["doc_id"] == lead["doc_id"] and matches(candidate, lead)]
        same_attribute = [candidate for candidate in candidates if candidate["doc_id"] == lead["doc_id"] and candidate["attribute"] == lead["attribute"] and candidate["evidence"]["page"] == lead["pdf_page"]]
        output.append({"lead_id": lead["lead_id"], "doc_id": lead["doc_id"], "pdf_page": lead["pdf_page"], "model": lead["model"],
                       "attribute": lead["attribute"], "field_match": bool(found), "assertion_ids": [candidate["assertion_id"] for candidate in found],
                       "same_page_attribute_candidates": len(same_attribute),
                       "interpretation": "Selected fields match; condition/component correctness still requires review." if found else "Miss or conservative abstention; inspect OCR, labels and model applicability."})
    return {"matched": sum(item["field_match"] for item in output), "denominator": len(leads), "leads": output}


def audit_decoders(record, source):
    """A decode check, not visual quality or OCR accuracy validation.

    Low display resolution still decodes original compressed image streams.
    Recovered format errors leave page evidence incomplete and must be explicit.
    """
    import pymupdf
    if hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]:
        raise RuntimeError("Decoder audit source digest mismatch")
    failures = []
    with pymupdf.open(source) as pdf:
        for index in range(len(pdf)):
            pymupdf.TOOLS.mupdf_warnings(reset=True)
            error = None
            try:
                pdf[index].get_pixmap(matrix=pymupdf.Matrix(.5, .5), alpha=False)
                warnings = pymupdf.TOOLS.mupdf_warnings(reset=True)
                if warnings and any(term in warnings.lower() for term in ("format error", "invalid code", "cannot decode", "truncated", "premature end")):
                    error = warnings[:400]
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            if error:
                record["pages"][index].update(status="failed", text="", lines=[], error="decoder_audit: " + error)
                failures.append({"page": index + 1, "error": error})
    successes = sum(page["status"] == "ok" for page in record["pages"])
    total = len(record["pages"])
    record["coverage"] = {"total_pages": total, "successful_pages": successes, "failed_pages": total - successes, "fraction": successes / total if total else 0}
    record["processing_status"] = "complete" if successes == total else "partial"
    record["decoder_audit"] = {"render_dpi": 36, "source_sha256": record["sha256"], "failed_pages": failures, "purpose": "Image-stream decode check, not OCR accuracy or visual completeness review."}
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default="runs/real-workspace")
    parser.add_argument("--skip-ingest", action="store_true", help="Require already-ingested records rather than reprocessing.")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip optional independent local OCR of three real pages.")
    parser.add_argument("--reextract", action="store_true", help="Reinterpret saved pages with current parser and invalidate old approvals without OCR.")
    parser.add_argument("--category-evidence", help="Apply a source-SHA-checked model-category evidence map before re-extraction.")
    parser.add_argument("--audit-decoders", action="store_true", help="Render all original pages at36dpi, mark damaged streams unknown, then reextract.")
    args = parser.parse_args()
    entries = [json.loads(line) for line in (ROOT / "data/corpus-manifest.jsonl").read_text("utf-8").splitlines() if line.strip()]
    admitted = [entry for entry in entries if entry.get("admission_status") == "admitted"]
    leads = [lead for lead in read_json(ROOT / "data/corpus/evidence-leads.json")["leads"] if lead["admission_status"] == "admitted"]
    workspace = Workspace(ROOT / args.workspace)
    started = time.perf_counter()
    if not args.skip_ingest:
        with python_network_blocked():
            # One-entry manifests enable useful progress checkpoints between books.
            for entry in admitted:
                manifest = ROOT / "runs/extraction-evaluation/current-manifest.jsonl"
                local = dict(entry, base=str(ROOT), path=entry["path"])
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(json.dumps(local) + "\n", "utf-8")
                print(json.dumps({"event": "ingest_start", "doc_id": entry["document"]["doc_id"]}), flush=True)
                summary = workspace.ingest_manifest(manifest)
                print(json.dumps({"event": "ingest_complete", "summary": summary}), flush=True)
    records = [workspace.record(entry["document"]["doc_id"]) for entry in admitted]
    if args.audit_decoders:
        if not args.reextract:
            raise ValueError("--audit-decoders requires --reextract")
        for record in records:
            entry = next(item for item in admitted if item["document"]["doc_id"] == record["document"]["doc_id"])
            print(json.dumps({"event": "decoder_audit_start", "doc_id": record["document"]["doc_id"]}), flush=True)
            audit_decoders(record, ROOT / entry["path"])
            print(json.dumps({"event": "decoder_audit_complete", "doc_id": record["document"]["doc_id"], "failed_pages": record["decoder_audit"]["failed_pages"]}), flush=True)
    if args.category_evidence:
        if not args.reextract:
            raise ValueError("--category-evidence requires --reextract to invalidate stale approvals")
        categories = read_json(ROOT / args.category_evidence)["documents"]
        for record in records:
            mapping = categories.get(record["document"]["doc_id"])
            if mapping:
                if mapping["document_sha256"] != record["sha256"] or not set(mapping["model_categories"]) <= set(record["document"]["models"]):
                    raise ValueError("Category evidence source identity/model mismatch")
                record["document"]["model_categories"] = mapping["model_categories"]
    if args.reextract:
        records = [reextract_record(record) for record in records]
        for record in records:
            write_json(workspace.record_path(record["document"]["doc_id"]), record)
    signature = processing_signature()
    for record in records:
        expected = next(entry["sha256"] for entry in admitted if entry["document"]["doc_id"] == record["document"]["doc_id"])
        if record["sha256"] != expected:
            raise RuntimeError("Source digest differs from corpus manifest")
    layout = [candidate for record in records for candidate in record["assertions"]]
    baseline = [candidate for record in records for candidate in extract_assertions(record["pages"], record["document"], method="baseline")]
    category_path = ROOT / (args.category_evidence or "data/corpus/model-category-evidence.json")
    category_digest = None
    if category_path.exists():
        evidence = read_json(category_path)["documents"]
        mapped_records = [record for record in records if record["document"].get("model_categories")]
        if mapped_records and all(
            evidence.get(record["document"]["doc_id"], {}).get("document_sha256") == record["sha256"]
            and evidence[record["document"]["doc_id"]]["model_categories"] == record["document"]["model_categories"]
            for record in mapped_records
        ):
            category_digest = hashlib.sha256(category_path.read_bytes()).hexdigest()
    report = {
        "schema_version": 1, "evaluation_kind": "development-source-inspected", "human_gold": False, "held_out": False,
        "scope": "Five admitted authentic scanned manuals, four named-product manuals plus one negative control; two further candidate-rights manuals excluded.",
        "source_label_description": "17 selected source-inspected leads from a collaborating agent; not exhaustive page annotations. Numeric/model/unit/qualifier/page fields compared, conditional semantics not automatically scored.",
        "not_claimed": ["real-world precision", "exhaustive recall", "full-assertion accuracy", "human validation", "unseen-family generalization", "OS-level network isolation"],
        "network_test": "Python socket connection functions blocked during ingestion and local OCR; not an operating-system firewall test.",
        "processing_signature": signature,
        "category_evidence_sha256": category_digest,
        "corpus": [{"doc_id": record["document"]["doc_id"], "sha256": record["sha256"], "processing_version": record["processing_version"],
                    "status": record["processing_status"], "coverage": record["coverage"],
                    "page_processing_version": record.get("page_processing_version", "legacy-composite-version"),
                    "extraction_version": record.get("extraction_version", "legacy-composite-version"),
                    "review_record_fingerprint": record_fingerprint(record),
                    "whole_record_digest": digest(record),
                    "model_categories": record["document"].get("model_categories", {}),
                    "decoder_audit": record.get("decoder_audit"),
                    "engines": dict(Counter(page.get("engine") or "failed" for page in record["pages"])),
                    "candidate_count": len(record["assertions"]), "warnings": record.get("warnings", []),
                    "failed_pages": [{"page": page["page_number"], "error": page["error"]} for page in record["pages"] if page["status"] != "ok"]} for record in records],
        "layout": {"candidate_count": len(layout), **lead_diagnostics(layout, leads)},
        "line_baseline": {"candidate_count": len(baseline), **lead_diagnostics(baseline, leads)},
        "fresh_ocr": [],
        "whole_output_development_audits": [{"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            **{key: read_json(path).get(key) for key in ("document_id", "record_fingerprint", "processing_version", "counts", "scoped_candidate_precision", "important_limit")}}
                                           for path in sorted((ROOT / "data/corpus").glob("m18-candidate-audit-v*.json"))],
        "resource_limits": {"render_pixels": signature["max_render_pixels"], "resume_attempts_per_page": signature["max_page_attempts"], "hard_per_page_timeout": False,
                            "limitation": "OCR/native decoding runs in-process; no hard per-page CPU/wall timeout or independent memory sandbox. A hung native call requires operator interruption."},
    }
    if not args.skip_ocr:
        import pymupdf
        selections = {"tm9-617-m18-1944": 12, "tm9-1752-homelite-1942": 3, "tm9-834-workshop-1944": 93}
        with python_network_blocked():
            for doc_id, number in selections.items():
                entry = next(entry for entry in admitted if entry["document"]["doc_id"] == doc_id)
                source = ROOT / entry["path"]
                identity = digest({"source": entry["sha256"], "page": number, "signature": signature})
                cache = ROOT / "runs/extraction-evaluation/ocr-pages" / f"{identity}.json"
                start = time.perf_counter()
                print(json.dumps({"event": "fresh_ocr_start", "doc_id": doc_id, "page": number}), flush=True)
                if cache.exists():
                    processed = read_json(cache)
                    cache_hit = True
                else:
                    with pymupdf.open(source) as pdf:
                        try:
                            processed = _read_page(pdf[number - 1], True)
                        except Exception as exc:
                            processed = {"page_number": number, "status": "failed", "engine": None, "text": "", "lines": [], "error": f"{type(exc).__name__}: {exc}"}
                    write_json(cache, processed)
                    cache_hit = False
                document = next(record["document"] for record in records if record["document"]["doc_id"] == doc_id)
                candidates = extract_assertions([processed], document)
                subset = [lead for lead in leads if lead["doc_id"] == doc_id and lead["pdf_page"] == number]
                result = {"doc_id": doc_id, "page": number, "status": processed["status"], "engine": processed.get("engine"),
                          "error": processed.get("error"), "cache_hit": cache_hit, "seconds": round(time.perf_counter() - start, 3),
                          "candidate_count": len(candidates), **lead_diagnostics(candidates, subset)}
                report["fresh_ocr"].append(result)
                print(json.dumps({"event": "fresh_ocr_complete", "result": result}), flush=True)
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    write_json(ROOT / "reports/extraction-development.json", report)
    markdown = ["# Extraction development diagnostics", "", "Authentic scan inputs; selected agent-inspected references. **Not human gold or held-out accuracy.**", "",
                f"Processed {len(records)} admitted manuals, {sum(len(record['pages']) for record in records)} pages. "
                f"Successful pages: {sum(record['coverage']['successful_pages'] for record in records)}. "
                f"Automatic candidates: {len(layout)} layout / {len(baseline)} line baseline.", "",
                "| Method | Selected reference field matches | Denominator |", "| --- | ---: | ---: |",
                f"| Layout | {report['layout']['matched']} | {len(leads)} |", f"| Line baseline | {report['line_baseline']['matched']} | {len(leads)} |", "",
                "Denominator: all 17 admitted development leads. Match requires document, source page, exact model, attribute, canonical unit, value/range and rating qualifier. "
                "Conditions and component meaning need review; a field match is not automatically a correct full assertion. Unmatched candidates are unlabelled, so precision is unknown. "
                "Selected leads cannot measure exhaustive recall. All source families were inspected during development; no generalization claim.", "",
                "Page success counts describe extraction execution. A separate36dpi decode audit, when present, identifies recovered image-stream errors and downgrades affected pages to unknown; it does not certify OCR text or visual completeness.", "",
                "| Manual | Pages OK / total | Candidates | Status |", "| --- | ---: | ---: | --- |"]
    for item in report["corpus"]:
        markdown.append(f"| {item['doc_id']} | {item['coverage']['successful_pages']} / {item['coverage']['total_pages']} | {item['candidate_count']} | {item['status']} |")
    markdown += ["", "## Fresh local OCR on actual scan pages", "", "The original PDF pages were rasterized in memory; no synthetic degradation or replacement source. Python network connection functions were blocked. "
                 "This verifies that local assets ran without Python network calls, not an OS firewall boundary. "
                 "The same document/model-category metadata is used for saved-page and fresh-OCR extraction; cached OCR output is reused when its source/page/engine identity matches.", "", "| Manual/page | Status | Candidates | Selected field matches |", "| --- | --- | ---: | ---: |"]
    for item in report["fresh_ocr"]:
        markdown.append(f"| {item['doc_id']} / {item['page']} | {item['status']} | {item['candidate_count']} | {item['matched']} / {item['denominator']} |")
    markdown += ["", "## Preserved whole-output development audits", "", "These audits inspect every emitted candidate in a specific frozen M18 record, using original source pixels. They remain agent development audits; the rubric was applied after inspecting candidates."]
    for audit in report["whole_output_development_audits"]:
        markdown.append(f"- `{audit['path']}`: {audit['counts']}; pinned record `{audit['record_fingerprint']}`. {audit['important_limit']}")
    markdown += ["", "## Remaining extraction roadblocks", "", "- Sparse OCR, damaged glyphs and split model identifiers can change applicability; unresolved identity must abstain.",
                 "- Prose specifications with implicit subjects and component-to-assembly relationships require stronger contextual parsing and reviewed labels.",
                 "- Electrical/mechanical roles, discrete ratings, governed/rated/no-load conditions, unit assumptions and revision scope need source review.",
                 "- Field/lead matches omit full condition correctness. Build exhaustive human annotations before reporting precision/recall or declaring A3/A10 complete.",
                 "- Broad authentic low-quality, multi-model, multilingual and unseen-layout coverage remains unproven.", "",
                 "- Rendering has a24M-pixel cap and failed pages have a3-attempt automatic resume budget. No hard per-page timeout or isolated process/memory sandbox exists; a hung native/OCR call needs operator interruption.", "",
                 "Reproduce from frozen workspace: `.venv/Scripts/python.exe scripts/evaluate_extraction.py --skip-ingest`. "
                 "A fresh rebuild requires ingestion, followed by explicit source-bound Homelite page 3 OCR "
                 "(`python -m vopt reocr --workspace runs/real-workspace --doc-id tm9-1752-homelite-1942 --pages 3`), "
                 "then category evidence and decoder audit before freezing reviews "
                 "(`.venv/Scripts/python.exe scripts/evaluate_extraction.py --skip-ingest --reextract --audit-decoders --category-evidence data/corpus/model-category-evidence.json`). "
                 "Detailed hashes, page failures, engine counts and per-lead results: `reports/extraction-development.json`.", ""]
    (ROOT / "reports/extraction-development.md").write_text("\n".join(markdown), "utf-8")
    print(json.dumps({"event": "complete", "layout": report["layout"]["matched"], "baseline": report["line_baseline"]["matched"], "denominator": len(leads), "elapsed_seconds": report["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()

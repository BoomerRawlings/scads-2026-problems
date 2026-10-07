"""Package the admitted public research corpus and frozen private evaluation state.

This is an extraction-side reproduction artifact, never a discovery catalog.
It includes full source content. No network operation, publication, or deletion.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vopt.io import canonical, digest, read_json
from vopt.review import record_fingerprint

WORKSPACE = "runs/real-workspace"
AUDITS = ("data/corpus/m18-candidate-audit-v1.json", "data/corpus/m18-candidate-audit-v2.json")
REPORTS = ("acceptance-status.md", "extraction-development.json", "extraction-development.md",
           "independent-core-audit.md", "retrieval-development.json", "retrieval-development.md", "scaling.json")


def safe_name(name):
    if not isinstance(name, str):
        raise ValueError("Archive paths must be strings")
    path = Path(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive path: {name}")
    if not name or path.as_posix() != name:
        raise ValueError(f"Noncanonical archive path: {name}")
    return name


def source_bytes(relative):
    safe_name(relative)
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Source leaves project: {relative}")
    return path.read_bytes()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    out, workspace = args.out.resolve(), args.workspace.resolve()
    if out.exists():
        raise ValueError("Output already exists; choose a new artifact path")
    if workspace != (ROOT / WORKSPACE).resolve():
        raise ValueError(f"This frozen development artifact requires {WORKSPACE}")
    if not (ROOT / "reports/acceptance-status.md").is_file():
        raise ValueError("Write the measured acceptance status before packaging")
    entries = [json.loads(line) for line in (ROOT / "data/corpus-manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    admitted = {e["document"]["doc_id"]: e for e in entries if e["admission_status"] == "admitted"}
    admitted_paths = {safe_name(e["path"]) for e in admitted.values()}
    excluded = [e for e in entries if e["admission_status"] != "admitted"]
    payload = {}
    def add(name, data):
        safe_name(name)
        if name.lower().endswith(".pdf") and name not in admitted_paths:
            raise ValueError(f"Unadmitted original PDF cannot enter archive: {name}")
        if name in payload:
            if payload[name] != data:
                raise ValueError(f"Archive entry collision: {name}")
        payload[name] = data
    for entry in admitted.values():
        data = source_bytes(entry["path"])
        if len(data) != entry["byte_size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Original source changed: {entry['document']['doc_id']}")
        add(entry["path"], data)
        for relative in entry["evidence_paths"]:
            add(relative, source_bytes(relative))
    fingerprints, records = {}, {}
    for path in sorted((workspace / "records").glob("*.json")):
        record = read_json(path)
        doc_id = record["document"]["doc_id"]
        if doc_id not in admitted:
            raise ValueError(f"Workspace contains unadmitted document {doc_id}")
        if record["sha256"] != admitted[doc_id]["sha256"]:
            raise ValueError(f"Record/source hash mismatch: {doc_id}")
        before = record_fingerprint(record)
        record["source_path"] = admitted[doc_id]["path"]
        assert record_fingerprint(record) == before
        fingerprints[doc_id] = before
        records[doc_id] = record
        add(f"{WORKSPACE}/records/{doc_id}.json", canonical(record))
    if set(fingerprints) != set(admitted):
        raise ValueError("Frozen workspace must contain every admitted source")
    for relative in ("data/corpus-manifest.jsonl", "data/corpus/evidence-leads.json", "data/corpus/model-category-evidence.json",
        "data/corpus/pdf-inventory.json", "data/corpus/evidence/snapshots.json", "data/corpus-research.md",
        "data/queries-development.json", "examples/agent-review-decisions.json", "scripts/prepare_development_release.py",
        "scripts/acquire_corpus.py", "scripts/package_research.py", "runs/development-coverage.json", "runs/development-values.json"):
        add(relative, source_bytes(relative))
    lead_data = read_json(ROOT / "data/corpus/evidence-leads.json")
    leads = lead_data["leads"]
    for lead in leads:
        if lead["doc_id"] in admitted:
            relative = lead["evidence_image"]
            add(relative, source_bytes(relative))
    for relative in AUDITS:
        audit = read_json(ROOT / relative)
        doc_id = audit["document_id"]
        if doc_id not in admitted or audit["document_sha256"] != admitted[doc_id]["sha256"]:
            raise ValueError("Audit document/source identity mismatch")
        if audit["human_gold"] is not False or audit["reviewer_kind"] != "agent":
            raise ValueError("Expected explicitly agent-reviewed development audit")
        if relative.endswith("-v2.json") and audit["record_fingerprint"] != fingerprints[doc_id]:
            raise ValueError("Post-fix audit is stale")
        if relative.endswith("-v2.json") and {a["assertion"]["assertion_id"] for a in audit["items"]} != {a["assertion_id"] for a in records[doc_id]["assertions"]}:
            raise ValueError("Post-fix audit does not cover every emitted candidate")
        for item in audit["items"]:
            if digest(item["assertion"]) != item["candidate_sha256"]:
                raise ValueError("Audit candidate integrity mismatch")
            data = source_bytes(item["source_image"])
            if hashlib.sha256(data).hexdigest() != item["source_image_sha256"]:
                raise ValueError("Audit image differs from inspected pixels")
            add(item["source_image"], data)
        add(relative, source_bytes(relative))
    for name in REPORTS:
        add(f"reports/{name}", source_bytes(f"reports/{name}"))
    for name in ("README.md", "RUNBOOK.md", "ACCEPTANCE.md", "ROADMAP.md", "CORPUS.md"):
        add(name, source_bytes(name))
    for path in sorted((ROOT / "docs").rglob("*.md")):
        relative = path.relative_to(ROOT).as_posix()
        add(relative, source_bytes(relative))

    # Backup to memory: consistent SQLite snapshot, with no temporary files or deletions.
    source = sqlite3.connect((workspace / "reviews.sqlite3").as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(":memory:")
    target.row_factory = sqlite3.Row
    try:
        source.backup(target)
        events = [dict(row) for row in target.execute("SELECT * FROM review_events ORDER BY event_id")]
        if any(event["actor_kind"] != "agent" for event in events):
            raise ValueError("This artifact is explicitly agent-reviewed; unexpected reviewer kind")
        spec = read_json(ROOT / "examples/agent-review-decisions.json")
        if spec["reviewer_kind"] != "agent" or spec["human_gold"] is not False or spec["workspace"] != WORKSPACE or spec["source_leads_canonical_sha256"] != digest(lead_data):
            raise ValueError("Frozen review plan/source references changed")
        latest = {(event["doc_id"], event["assertion_id"]): event for event in events}
        reviewed_count = 0
        for plan in spec["documents"]:
            doc_id = plan["doc_id"]
            if fingerprints[doc_id] != plan["record_fingerprint"]:
                raise ValueError("Frozen review plan no longer matches candidate records")
            candidates = {a["assertion_id"]: a for a in records[doc_id]["assertions"]}
            for decision in plan["decisions"]:
                if digest(candidates[decision["assertion_id"]]) != decision["candidate_sha256"]:
                    raise ValueError("Reviewed candidate changed")
                event = latest.get((doc_id, decision["assertion_id"]))
                if not event or event["fingerprint"] != fingerprints[doc_id] or event["decision"] != decision["decision"] or json.loads(event["correction"]) != decision.get("correction", {}) or event["reason"] != decision["reason"] or event["actor"] != "development-source-review-agent":
                    raise ValueError("Review ledger does not match frozen decisions")
                lead = next(item for item in leads if item["lead_id"] == decision["lead_id"])
                if hashlib.sha256(payload[lead["evidence_image"]]).hexdigest() != decision["evidence_image_sha256"]:
                    raise ValueError("Reviewed source image changed")
                reviewed_count += 1
        add(f"{WORKSPACE}/reviews.sqlite3", target.serialize())
    finally:
        target.close()
        source.close()
    add("RESTORE.txt", (
        "EXTRACTION-SIDE RESEARCH ARTIFACT: contains original documents and OCR.\n"
        "Never import this archive into metadata-only discovery.\n\n"
        "Extract into a new directory. Run from that directory with a qualified VOPT extraction runtime:\n"
        "  <portable-extraction>/vopt.cmd serve --workspace runs/real-workspace --port 8763\n"
        "The records use relative source paths; keep this working directory for review rendering.\n"
        "Review fingerprints exclude runtime source paths. All other evidence remains pinned.\n"
        "Verify/replay the existing agent reviews and regenerate metadata catalogs (no new approvals):\n"
        "  <portable-extraction>/runtime/python.exe -I scripts/prepare_development_release.py --workspace runs/real-workspace --apply\n"
        "That command must report zero new review events and the same two release integrity hashes.\n"
        "Inspect reports and examples/agent-review-decisions.json for agent-only approval provenance.\n"
        "Both original and post-fix M18 audits, including all referenced PNGs, are retained.\n"
        "Original rights scope is documented per source. Candidate PDFs and their source images are excluded;\n"
        "manifest/lead/report references to those candidates are retained and explicitly marked unadmitted.\n"
        "Reports describe this frozen source/evaluation snapshot and may predate final runtime qualification.\n"
        "Engineering packaging proofs are separate artifacts; see the final delivery's build verification.\n"
        "This artifact is local reproduction evidence, not human gold or an accredited release.\n").encode())
    manifest = {"schema_version": 1, "artifact_type": "private-extraction-research", "contains_source_content": True,
        "human_gold": False, "source_count": len(admitted), "record_fingerprints": fingerprints,
        "workspace": WORKSPACE, "review_event_count": len(events), "pinned_reviewed_candidates": reviewed_count,
        "included_audits": list(AUDITS), "report_scope": "frozen source/evaluation snapshot; final engineering qualification is separate",
        "excluded_sources": [{"doc_id": e["document"]["doc_id"], "path": e["path"], "admission_status": e["admission_status"],
                              "original_included": False, "source_images_included": False} for e in excluded],
        "files": [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(payload.items())]}
    payload["research-manifest.json"] = canonical(manifest)
    if any(lead["evidence_image"] in payload for lead in leads if lead["doc_id"] not in admitted):
        raise ValueError("Excluded candidate source image entered archive")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    with zipfile.ZipFile(out) as archive:
        for item in manifest["files"]:
            if hashlib.sha256(archive.read(item["path"])).hexdigest() != item["sha256"]:
                raise ValueError("Archive verification failed")
        if {name for name in archive.namelist() if name.lower().endswith(".pdf")} != admitted_paths:
            raise ValueError("Archive original-document admission mismatch")
    print(json.dumps({"status": "verified", "files": len(payload), "originals": len(admitted), "bytes": out.stat().st_size,
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "review_events": len(events),
        "audits": list(AUDITS), "excluded_originals": len(excluded), "human_gold": False}, indent=2))


if __name__ == "__main__":
    main()

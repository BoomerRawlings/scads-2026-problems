"""Replay pinned, source-inspected AGENT decisions; never create human gold.

Run from the project root after the real extraction is frozen:
  python scripts/prepare_development_release.py --workspace runs/real-workspace
  python scripts/prepare_development_release.py --workspace runs/real-workspace --apply

The first command checks only. Existing differing reviews/releases are refused.
Missing extraction candidates remain missing; unselected candidates stay pending.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from vopt.catalog import Catalog
from vopt.io import digest, read_json, write_json
from vopt.release import export_bundle
from vopt.review import record_fingerprint
from vopt.schema import require, validate_review_candidate
from vopt.workspace import Workspace

ACTOR = "development-source-review-agent"
SPEC = PROJECT / "examples/agent-review-decisions.json"
LEADS = PROJECT / "data/corpus/evidence-leads.json"
MANIFEST = PROJECT / "data/corpus-manifest.jsonl"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def local_path(relative):
    require(isinstance(relative, str), "Expected project-relative path")
    path = (PROJECT / relative).resolve()
    require(path.is_relative_to(PROJECT), "Path leaves the project")
    return path


class PlannedApprovals:
    """In-memory desired state for validating the release before any mutation."""
    def __init__(self, approved):
        self.approved_by_doc = approved

    def status(self, record):
        return {"items": []}

    def approved(self, record, required_kind=None):
        require(required_kind == "agent", "Development planning requires agent scope")
        return copy.deepcopy(self.approved_by_doc[record["document"]["doc_id"]])


def prepare(workspace, apply=False):
    workspace = Path(workspace).resolve()
    require(workspace == PROJECT / "runs/real-workspace", "Only runs/real-workspace is authorized")
    require((workspace / "records").is_dir(), "Real extraction records are not ready")
    spec = read_json(SPEC)
    require(spec["schema_version"] == 1 and spec["reviewer_kind"] == "agent" and spec["human_gold"] is False,
            "Only explicitly agent-reviewed development decisions are supported")
    require(spec["workspace"] == "runs/real-workspace", "Wrong pinned workspace")
    lead_data = read_json(LEADS)
    require(digest(lead_data) == spec["source_leads_canonical_sha256"], "Source references changed; review the plan again")
    leads = {lead["lead_id"]: lead for lead in lead_data["leads"]}
    admitted = {entry["document"]["doc_id"]: entry for entry in
                (json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip())
                if entry["admission_status"] == "admitted"}
    ws = Workspace(workspace)
    records, planned, actions, seen = [], {}, [], set()
    for document_plan in spec["documents"]:
        doc_id = document_plan["doc_id"]
        require(doc_id in admitted and doc_id not in seen, "Unadmitted or duplicate document")
        seen.add(doc_id)
        entry = admitted[doc_id]
        record = ws.record(doc_id)
        require(record["sha256"] == document_plan["document_sha256"] == entry["sha256"], "Source identity changed")
        source = local_path(entry["path"])
        require(source.stat().st_size == entry["byte_size"] and sha256(source) == entry["sha256"], "Source bytes changed")
        require(record["document"]["rights"] == entry["document"]["rights"], "Rights declaration changed")
        require(record_fingerprint(record) == document_plan["record_fingerprint"], "Extraction changed; inspect new candidates before reviewing")
        status = ws.reviews.status(record)
        items = {item["assertion"]["assertion_id"]: item for item in status["items"]}
        approved, used = [], set()
        for decision in document_plan["decisions"]:
            assertion_id = decision["assertion_id"]
            require(assertion_id in items and assertion_id not in used, "Missing or duplicate extraction candidate")
            used.add(assertion_id)
            item, lead = items[assertion_id], leads[decision["lead_id"]]
            require(lead["admission_status"] == "admitted" and lead["human_gold"] is False, "Invalid development source reference")
            require(lead["doc_id"] == doc_id and lead["document_sha256"] == record["sha256"], "Reference identity mismatch")
            require(digest(item["assertion"]) == decision["candidate_sha256"], "Exact extraction candidate changed")
            require(item["assertion"]["evidence"]["page"] == lead["pdf_page"] == decision["source_page"], "Reference page mismatch")
            require(sha256(local_path(lead["evidence_image"])) == decision["evidence_image_sha256"], "Inspected source image changed")
            require(decision["decision"] in ("accept", "correct"), "This plan contains approved observations only")
            correction = decision.get("correction", {})
            require((decision["decision"] == "correct") == bool(correction), "Correction decision mismatch")
            effective = {**item["assertion"], **correction, "status": "reviewed"}
            validate_review_candidate(effective, record["document"])
            for field in ("model", "attribute", "value", "value_max", "unit", "qualifier"):
                require(effective.get(field) == lead.get(field), f"Reviewed {field} differs from pinned source reference")
            require(effective.get("conditions", []) == lead.get("conditions", []), "Source conditions differ")
            require(effective.get("variant") is None, "Unexpected variant scope")
            event = item["event"]
            if event:
                require(item["review_status"] == decision["decision"] and event["actor_kind"] == "agent"
                        and event["actor"] == ACTOR and event["correction"] == correction
                        and event["reason"] == decision["reason"], "Existing review differs; no automatic overwrite permitted")
            else:
                actions.append((record, decision))
            approved.append(effective)
        # Do not silently include approvals absent from this frozen source-review plan.
        require({a["assertion_id"] for a in ws.reviews.approved(record, required_kind="agent")} <= used,
                "Workspace contains agent approvals outside this plan")
        records.append(record)
        planned[doc_id] = approved
    require(seen == set(admitted), "Plan must explicitly account for every admitted document")

    preview = PlannedApprovals(planned)
    bundles = {profile: export_bundle(records, preview, f"vopt-development-{profile}", 1, profile,
                                     required_kind="agent", require_all_reviewed=False)
               for profile in ("coverage", "values")}
    for profile, bundle in bundles.items():
        output = PROJECT / f"runs/development-{profile}.json"
        if output.exists():
            require(read_json(output) == bundle, "Existing development bundle differs; use a deliberately versioned new plan")
        catalog = PROJECT / f"runs/development-{profile}.sqlite3"
        if catalog.exists():
            info = Catalog(catalog, readonly=True).info()
            require(info.get("integrity") == bundle["integrity"], "Existing development catalog differs")
    if apply:
        for record, decision in actions:
            require(record_fingerprint(ws.record(record["document"]["doc_id"])) == record_fingerprint(record), "Extraction changed during review")
            ws.reviews.decide(record, decision["assertion_id"], decision["decision"], ACTOR, actor_kind="agent",
                              correction=decision.get("correction"), reason=decision["reason"],
                              expected_fingerprint=record_fingerprint(record), expected_event_id=0)
        for record in records:
            require(record_fingerprint(ws.record(record["document"]["doc_id"])) == record_fingerprint(record), "Extraction changed before release")
        for profile, bundle in bundles.items():
            actual = export_bundle(records, ws.reviews, f"vopt-development-{profile}", 1, profile,
                                   required_kind="agent", require_all_reviewed=False)
            require(actual == bundle, "Review state changed before release")
            write_json(PROJECT / f"runs/development-{profile}.json", actual)
            Catalog(PROJECT / f"runs/development-{profile}.sqlite3").import_bundle(actual)
    return {"mode": "applied" if apply else "checked", "reviewer_kind": "agent", "human_gold": False,
            "documents": len(records), "source_reviewed_candidates": sum(len(x) for x in planned.values()),
            "new_review_events": len(actions) if apply else 0, "planned_review_events": len(actions),
            "remaining_unreviewed_candidates": sum(len(r["assertions"]) - len(planned[r["document"]["doc_id"]]) for r in records),
            "release_integrity": {profile: bundle["integrity"] for profile, bundle in bundles.items()},
            "limitations": "Selected, agent-corrected development observations only; missing candidates remain missing. Not human gold or an accuracy benchmark."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Explicitly name runs/real-workspace")
    parser.add_argument("--apply", action="store_true", help="Append agent-only reviews and create the two development releases")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.workspace, args.apply), indent=2))
    except (KeyError, ValueError, OSError) as exc:
        parser.exit(1, f"Development release refused: {exc}\n")


if __name__ == "__main__":
    main()

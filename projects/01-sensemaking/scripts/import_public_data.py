"""Offline, conservative import of the fixed ROR/Wikidata capture.

Default: verify and describe the import. --import-data creates a NEW directory.
No network calls, identity merging, linked-media reads, or model-generated text.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile

try:
    from . import capture_public_data as capture
except ImportError:
    import capture_public_data as capture

VERSION = "1"
INDEXED_PROPERTIES = {"P31", "P749", "P355", "P361", "P527", "P1365", "P1366", "P6782"}
RELATION_PROPERTIES = {"P749", "P355", "P361", "P527", "P1365", "P1366"}
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
CAUTION = (
    "Source assertions, not independently verified facts. Edit/retrieval dates are not relationship validity dates. "
    "Projection records a captured assertion, not present-day truth. Crosswalks never merge identities; "
    "reciprocity does not establish independent corroboration. Linked media was not imported."
)


class ImportError(ValueError):
    """Invalid capture or unsafe destination."""


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def node_id(provider: str, identifier: str) -> str:
    return provider + ":" + identifier.lower()


def wd_value(statement):
    snak = statement.get("mainsnak", {})
    return snak.get("datavalue", {}).get("value") if snak.get("snaktype") == "value" else None


def item_target(statement):
    value = wd_value(statement)
    return value.get("id") if isinstance(value, dict) and value.get("entity-type") == "item" else None


def statement_reasons(statement):
    reasons = []
    if statement.get("rank") not in {"normal", "preferred"}:
        reasons.append("deprecated_or_unknown_rank")
    if statement.get("mainsnak", {}).get("snaktype") != "value":
        reasons.append("unknown_or_no_value")
    if statement.get("qualifiers"):
        reasons.append("qualified_claim_requires_scope_review")
    return reasons


def load_sources(directory: Path):
    directory = directory.resolve()
    manifest_path = directory / "capture-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ImportError("capture_manifest_missing_oversized_or_linked")
    manifest_bytes = manifest_path.read_bytes()
    # The acquisition verifier validates fixed URLs, IDs, exact revisions, sizes and hashes.
    capture.verify_capture(directory)
    if manifest_path.read_bytes() != manifest_bytes:
        raise ImportError("capture_manifest_changed_during_verification")
    manifest = json.loads(manifest_bytes)
    if manifest["totals"]["raw_bytes"] > capture.POLICY["maximum_received_bytes_per_run"]:
        raise ImportError("capture_total_byte_limit")
    entries = {entry["id"]: entry for entry in manifest["sources"]}
    sources = []
    for spec in sorted(capture.SOURCES, key=lambda item: item["id"]):
        path = directory / capture.raw_path(spec)
        if path.is_symlink() or not path.resolve().is_relative_to(directory):
            raise ImportError("linked_source_rejected")
        raw = path.read_bytes()
        entry = entries[spec["id"]]
        if len(raw) != entry["size_bytes"] or capture.digest(raw) != entry["sha256"]:
            raise ImportError("source_changed_during_import")
        if capture.validate_response(spec, raw) != entry["revision"]:
            raise ImportError("source_revision_changed_during_import")
        data = json.loads(raw)
        entity = data if spec["provider"] == "ror" else data["entities"][spec["entity_id"]]
        sources.append({"spec": spec, "entry": entry, "raw": raw, "entity": entity})
    return sources, manifest_bytes


def make_node(source):
    spec, entity = source["spec"], source["entity"]
    identifier = node_id(spec["provider"], spec["entity_id"])
    if spec["provider"] == "ror":
        names = entity["names"]
        name = next((n["value"] for n in names if "ror_display" in n["types"]), names[0]["value"])
        aliases = [n["value"] for n in names]
    else:
        name = entity.get("labels", {}).get("en", {}).get("value", spec["entity_id"])
        aliases = [n["value"] for n in entity.get("aliases", {}).get("en", [])]
    return {"id": identifier, "name": name,
            "aliases": sorted(set([spec["entity_id"], *aliases]) - {name}),
            "provider": spec["provider"], "source_entity_id": spec["entity_id"],
            "identity_policy": "Source-specific identity; no cross-database merge."}


def build_dataset(sources, capture_bytes: bytes):
    """Pure deterministic projection; full source bytes remain separately inspectable."""
    nodes = [make_node(source) for source in sources]
    known = {node["id"] for node in nodes}
    by_node = {node["id"]: source for node, source in zip(nodes, sources)}
    ledger = []
    crosswalk_claims = []
    extracts = {}
    edges = {}
    files = {"sources/capture-manifest.json": capture_bytes}
    rows = []
    evidence_manifest = []

    for source, node in zip(sources, nodes):
        spec, entry, entity = source["spec"], source["entry"], source["entity"]
        current, evidence_id = node["id"], "claims-" + spec["id"]
        raw_path = "sources/" + entry["path"]
        files[raw_path] = source["raw"]
        provenance = {**entry, "path": raw_path, "capture_manifest_path": "sources/capture-manifest.json"}
        selected = []
        decisions = []
        if spec["provider"] == "ror":
            for index, relationship in enumerate(entity.get("relationships", [])):
                target = node_id("ror", relationship["id"].removeprefix("https://ror.org/"))
                kind = relationship["type"]
                reasons = []
                if kind not in {"parent", "child"}:
                    reasons.append("predicate_not_projected_to_contains")
                if entity.get("status") != "active":
                    reasons.append("source_record_not_active")
                if target not in known:
                    reasons.append("endpoint_not_captured")
                elif by_node[target]["entity"].get("status") != "active":
                    reasons.append("endpoint_record_not_active")
                decision = {"source_entity": current, "source_path": f"/relationships/{index}",
                            "predicate": kind, "target": target, "evidence_id": evidence_id,
                            "source_assertion": relationship, "exclusion_reasons": reasons}
                if not reasons:
                    decision["projected_edge"] = [target, current] if kind == "parent" else [current, target]
                decisions.append(decision)
            for index, external in enumerate(entity.get("external_ids", [])):
                if external["type"] == "wikidata":
                    for target in external["all"]:
                        if not re.fullmatch(r"Q[1-9][0-9]*", target):
                            raise ImportError("invalid_wikidata_crosswalk")
                        crosswalk_claims.append({"ror": current, "wikidata": node_id("wikidata", target),
                                                 "source_entity": current, "source_path": f"/external_ids/{index}",
                                                 "evidence_id": evidence_id, "source_assertion": external,
                                                 "exclusion_reasons": []})
            selected = {key: entity.get(key) for key in ("id", "names", "status", "admin", "established", "relationships", "external_ids")}
        else:
            selected = {"id": entity["id"], "lastrevid": entity["lastrevid"], "modified": entity["modified"],
                        "labels": {"en": entity.get("labels", {}).get("en")}, "claims": {}}
            for prop, statements in sorted(entity.get("claims", {}).items()):
                if prop in INDEXED_PROPERTIES:
                    selected["claims"][prop] = statements
                for index, statement in enumerate(statements):
                    pointer = f"/entities/{spec['entity_id']}/claims/{prop}/{index}"
                    reasons = statement_reasons(statement)
                    target_id = item_target(statement)
                    target = node_id("wikidata", target_id) if target_id else None
                    if prop not in {"P749", "P355"}:
                        reasons.append("predicate_not_projected_to_contains")
                    if prop in RELATION_PROPERTIES:
                        if target is None:
                            reasons.append("non_item_relationship_value")
                        elif target not in known:
                            reasons.append("endpoint_not_captured")
                    decision = {"source_entity": current, "source_path": pointer, "predicate": prop,
                                "statement_guid": statement.get("id"), "target": target,
                                "indexed": prop in INDEXED_PROPERTIES, "exclusion_reasons": reasons,
                                "raw_source_path": raw_path}
                    if prop in INDEXED_PROPERTIES:
                        decision["evidence_id"] = evidence_id
                    if prop in {"P749", "P355"} and target and not reasons:
                        decision["projected_edge"] = [target, current] if prop == "P749" else [current, target]
                    decisions.append(decision)
                    if prop == "P6782" and isinstance(wd_value(statement), str):
                        rid = wd_value(statement).removeprefix("https://ror.org/")
                        crosswalk_claims.append({"ror": node_id("ror", rid), "wikidata": current,
                                                 "source_entity": current, "source_path": pointer,
                                                 "evidence_id": evidence_id, "source_assertion": statement,
                                                 "exclusion_reasons": statement_reasons(statement)})
        for decision in decisions:
            ledger.append(decision)
            if "projected_edge" in decision:
                start, end = decision["projected_edge"]
                key = (start, end)
                edges.setdefault(key, set()).add(evidence_id)
        extracts[current] = {"source_provenance": provenance, "caution": CAUTION,
                             "literal_source_extract": selected,
                             "projection_decisions": [d for d in decisions if d.get("indexed", True)],
                             "unindexed_statement_count": sum(not d.get("indexed", True) for d in decisions)}
        rows.append({"id": "identity-" + spec["id"], "entity_id": current, "title": node["name"] + " — source identity",
                     "date": entry["retrieved_at_utc"][:10], "text": json.dumps({"identity": node, "source_provenance": provenance, "caution": CAUTION}, ensure_ascii=False, sort_keys=True),
                     "subject": current, "predicate": "captured_source_record", "value": entry["url"]})
        evidence_manifest.append({"id": evidence_id, "entity_ids": [current], "kind": "text",
                                  "title": node["name"] + " — source relationship and identity claims",
                                  "date": entry["retrieved_at_utc"][:10], "date_meaning": "capture date; not assertion validity",
                                  "path": "evidence/" + spec["id"] + ".json", "assertions": [],
                                  "extraction": "deterministic field selection; literal source JSON values retained",
                                  "provenance": provenance})

    pairs = {}
    for claim in crosswalk_claims:
        pairs.setdefault((claim["ror"], claim["wikidata"]), []).append(claim)
    crosswalks = []
    for (rid, wid), claims in sorted(pairs.items()):
        wd_source = by_node.get(wid)
        is_list = bool(wd_source and any(item_target(s) == "Q13406463" and not statement_reasons(s)
                                        for s in wd_source["entity"].get("claims", {}).get("P31", [])))
        reciprocal = {c["source_entity"] for c in claims if not c["exclusion_reasons"]} == {rid, wid}
        status = ("rejected_list_article_type" if is_list else "endpoint_not_captured" if rid not in known or wid not in known
                  else "reciprocal_candidate_requires_identity_review" if reciprocal else "unreciprocated_candidate")
        item = {"ror": rid, "wikidata": wid, "status": status, "merged": False, "claims": claims,
                "note": "Identifier assertions only; no equivalence edge or independence claim."}
        crosswalks.append(item)
        for identity in (rid, wid):
            if identity in extracts:
                extracts[identity].setdefault("crosswalk_candidates", []).append(item)

    for node, source in zip(nodes, sources):
        files["evidence/" + source["spec"]["id"] + ".json"] = encoded(extracts[node["id"]])
    for item in evidence_manifest:
        origin = item["entity_ids"][0]
        mentioned = {origin}
        for candidate in extracts[origin].get("crosswalk_candidates", []):
            mentioned.update(identity for identity in (candidate["ror"], candidate["wikidata"]) if identity in known)
        item["entity_ids"] = sorted(mentioned)
        item["entity_association"] = "Co-mentioned captured crosswalk candidates, including rejected ones; relevance only, not identity equivalence or a graph edge."
    graph = {"nodes": nodes, "edges": [{"source": start, "target": end, "relation": "contains", "evidence_ids": sorted(ids),
                                         "semantics": "Conservative projection of source assertions; no validity-date inference."}
                                        for (start, end), ids in sorted(edges.items())]}
    frontier = sorted({d["target"] for d in ledger if "endpoint_not_captured" in d["exclusion_reasons"] and d.get("target")} |
                      {i for x in crosswalks for i in (x["ror"], x["wikidata"]) if i not in known})
    totals = {"source_records": len(sources), "raw_bytes": sum(len(s["raw"]) for s in sources), "nodes": len(nodes),
              "edges": len(graph["edges"]), "indexed_evidence_records": len(rows) + len(evidence_manifest),
              "relationship_and_statement_decisions": len(ledger), "projected_source_assertions": sum("projected_edge" in d for d in ledger),
              "crosswalk_candidates": len(crosswalks), "frontier_entities": len(frontier),
              "unindexed_wikidata_statements": sum(not d.get("indexed", True) for d in ledger)}
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["id", "entity_id", "title", "date", "text", "subject", "predicate", "value"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    files["records.csv"] = buffer.getvalue().encode("utf-8")
    files["graph.json"] = encoded(graph)
    files["manifest.json"] = encoded(evidence_manifest)
    files["dataset.json"] = encoded({"id": "public-research-pilot", "name": "Captured ROR and Wikidata research identities", "kind": "public_snapshot",
                                      "version": VERSION, "license": "CC0 structured data; linked media excluded",
                                      "description": "Eight ROR records and four independently pinned Wikidata revisions. Separate source identities; conservative claim projection. " + CAUTION})
    files["projection-ledger.json"] = encoded({"decisions": ledger, "crosswalks": crosswalks, "frontier_entity_ids": frontier,
                                               "exclusion_counts": dict(sorted(Counter(reason for d in ledger for reason in d["exclusion_reasons"]).items())),
                                               "scope": "All ROR relationships and all Wikidata statements classified. Other ROR metadata and all unindexed source fields retained in exact raw files. Frontier covers relationship and identifier targets only; no recursive fetch."})
    files["import-manifest.json"] = encoded({"schema_version": 1, "importer_version": VERSION, "totals": totals,
                                            "capture_manifest_sha256": capture.digest(capture_bytes),
                                            "importer_sha256": capture.digest(Path(__file__).read_bytes()),
                                            "policy": {"network": "none", "identity_merging": "none", "indexed_wikidata_properties": sorted(INDEXED_PROPERTIES),
                                                       "wikidata_projection": "P749/P355 only; captured endpoints; normal/preferred rank; value snak; no qualifiers. Qualified claims retained, not flattened.",
                                                       "ror_projection": "Active captured endpoints; parent/child only. Related and succession claims excluded.",
                                                       "rank_note": "No best-rank collapse; all statements retained. Eligible statements are claims, never asserted current truth.",
                                                       "raw_evidence": "Byte-exact files under sources/raw; not automatically indexed or returned to models.",
                                                       "maximum_output_bytes": MAX_OUTPUT_BYTES},
                                            "files": [{"path": path, "sha256": capture.digest(raw), "size_bytes": len(raw)} for path, raw in sorted(files.items())]})
    if sum(map(len, files.values())) > MAX_OUTPUT_BYTES:
        raise ImportError("output_byte_limit")
    return files, totals


def import_dataset(capture_dir: Path, output_dir: Path | None = None):
    """Verify all inputs before any write. Refuse every existing destination."""
    if output_dir is not None and (output_dir.exists() or output_dir.is_symlink()):
        raise ImportError("output_exists_refusing_overwrite")
    sources, capture_bytes = load_sources(capture_dir)
    files, totals = build_dataset(sources, capture_bytes)
    if output_dir is None:
        return totals
    output_dir = output_dir.absolute()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # Stage only our fresh files; a failed import never leaves a partial dataset.
    with tempfile.TemporaryDirectory(prefix=".public-import-", dir=output_dir.parent) as temporary:
        stage = Path(temporary) / "dataset"
        stage.mkdir()
        for path, raw in sorted(files.items()):
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
        if output_dir.exists() or output_dir.is_symlink():
            raise ImportError("output_appeared_refusing_overwrite")
        stage.rename(output_dir)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, default=capture.DEFAULT_OUTPUT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--import-data", action="store_true")
    args = parser.parse_args()
    destination = (args.output_dir or args.capture_dir / "imported") if args.import_data else None
    try:
        result = import_dataset(args.capture_dir, destination)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "source_files": "unchanged"}))
        return 1
    print(json.dumps({"action": "imported" if destination else "verified_plan_no_writes", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

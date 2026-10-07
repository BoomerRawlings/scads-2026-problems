"""Project the verified fixed public capture into complete, addressable source units.

Offline plan by default; --import-data creates a fresh separate dataset. No model,
network, identity merging, source truncation or modification of the older import.
This does not implement bounded catalog retrieval in the agent harness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import tempfile

try:
    from . import import_public_data as legacy
except ImportError:
    import import_public_data as legacy

capture = legacy.capture
VERSION = "statement-units-v1"
MAX_RECORD_BYTES = 64 * 1024  # Full Workspace record JSON, not only source text.
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
CSV_HEADER = b"id,entity_id,title,date,text,subject,predicate,value\n"


class ProjectionError(ValueError):
    """A source unit cannot be represented faithfully within the declared bounds."""


def encoded(value):
    return legacy.encoded(value)


def pointer_value(document, pointer):
    """Read an exact JSON pointer; never interpret source prose as extraction rules."""
    value = document
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def unit_id(role, source_id, source_hash, pointer):
    address = encoded([source_id, source_hash, pointer])
    return role + "-" + source_id + "-" + hashlib.sha256(address).hexdigest()[:20]


def build_dataset(sources, capture_bytes):
    """Reuse conservative projection policy; change only evidence record granularity."""
    original, prior_totals = legacy.build_dataset(sources, capture_bytes)
    graph = json.loads(original["graph.json"])
    ledger = json.loads(original["projection-ledger.json"])
    files = {name: raw for name, raw in original.items() if name.startswith("sources/")}
    files["records.csv"] = CSV_HEADER
    source_by_entity = {legacy.node_id(item["spec"]["provider"], item["spec"]["entity_id"]): item for item in sources}
    node_by_id = {node["id"]: node for node in graph["nodes"]}
    decision_by_pointer = {(d["source_entity"], d["source_path"]): d for d in ledger["decisions"]}
    address_ids, manifest, seen = {}, [], set()
    role_counts = Counter()

    def provenance(source):
        return {**source["entry"], "path": "sources/" + source["entry"]["path"],
                "capture_manifest_path": "sources/capture-manifest.json"}

    def add_record(eid, role, entities, title, date, payload, origin):
        if eid in seen:
            raise ProjectionError("duplicate_source_unit_id")
        seen.add(eid)
        path = "evidence/" + eid + ".json"
        raw = encoded({"record_type": role, "caution": legacy.CAUTION, **payload})
        entry = {"id": eid, "entity_ids": sorted(entities), "kind": "text", "title": title,
                 "date": date, "date_meaning": ("earliest contributing capture date; not assertion validity or event time"
                                                if role == "crosswalk" else "capture date; not assertion validity or event time"),
                 "path": path, "assertions": [], "extraction": "complete literal source unit; deterministic provenance and projection metadata",
                 "provenance": origin}
        if len(entities) > 1:
            entry["entity_association"] = "Explicitly co-mentioned captured identities; relevance only, not identity equivalence or a graph edge."
        returned = {**entry, "source": path, "text": raw.decode("utf-8"), "sha256": capture.digest(raw)}
        returned_size = len(json.dumps(returned, ensure_ascii=False).encode("utf-8"))
        if returned_size > MAX_RECORD_BYTES:
            raise ProjectionError("complete_source_unit_exceeds_record_byte_limit:" + eid)
        files[path] = raw
        manifest.append(entry)
        role_counts[role] += 1

    def add_source_unit(source, role, pointer, title, fragments=None, decision=None, entities=None):
        spec = source["spec"]
        entity = legacy.node_id(spec["provider"], spec["entity_id"])
        eid = unit_id(role, spec["id"], source["entry"]["sha256"], pointer)
        address_ids[entity, pointer] = eid
        if fragments is None:
            document = json.loads(source["raw"])
            fragments = [{"json_pointer": pointer, "value": pointer_value(document, pointer)}]
        origin = provenance(source)
        payload = {"source_provenance": origin, "source_fragments": fragments}
        if decision is not None:
            decision["evidence_id"] = eid
            # The literal value already appears in source_fragments; no second source copy is needed.
            payload["projection_decision"] = {key: value for key, value in decision.items() if key != "source_assertion"}
        add_record(eid, role, entities or {entity}, title, source["entry"]["retrieved_at_utc"][:10], payload, origin)
        return eid

    for source in sources:
        spec, entity = source["spec"], source["entity"]
        current = legacy.node_id(spec["provider"], spec["entity_id"])
        name = node_by_id[current]["name"]
        prefix = "" if spec["provider"] == "ror" else "/entities/" + spec["entity_id"]
        fields = (tuple(sorted(set(entity) - {"relationships", "external_ids"})) if spec["provider"] == "ror"
                  else ("id", "type", "lastrevid", "modified", "labels", "aliases", "descriptions"))
        fragments = [{"json_pointer": prefix + "/" + key, "value": entity[key]} for key in fields if key in entity]
        add_source_unit(source, "identity", prefix or "/", name + " — source identity", fragments=fragments)
        if spec["provider"] == "ror":
            for index, relationship in enumerate(entity.get("relationships", [])):
                pointer = f"/relationships/{index}"
                add_source_unit(source, "relationship", pointer, name + " — ROR " + relationship["type"],
                                decision=decision_by_pointer[current, pointer])
            for index, external in enumerate(entity.get("external_ids", [])):
                pointer = f"/external_ids/{index}"
                mentions = {current}
                if external["type"] == "wikidata":
                    mentions.update(legacy.node_id("wikidata", wid) for wid in external["all"]
                                    if legacy.node_id("wikidata", wid) in node_by_id)
                add_source_unit(source, "external-id", pointer, name + " — " + external["type"] + " identifiers", entities=mentions)
        else:
            for prop, statements in sorted(entity.get("claims", {}).items()):
                if prop not in legacy.INDEXED_PROPERTIES:
                    continue
                for index, statement in enumerate(statements):
                    pointer = f"/entities/{spec['entity_id']}/claims/{prop}/{index}"
                    mentions = {current}
                    if prop == "P6782" and isinstance(legacy.wd_value(statement), str):
                        rid = legacy.node_id("ror", legacy.wd_value(statement).removeprefix("https://ror.org/"))
                        if rid in node_by_id:
                            mentions.add(rid)
                    add_source_unit(source, "statement", pointer, name + " — Wikidata " + prop,
                                    decision=decision_by_pointer[current, pointer], entities=mentions)

    for candidate in ledger["crosswalks"]:
        origins = []
        for claim in candidate["claims"]:
            claim["evidence_id"] = address_ids[claim["source_entity"], claim["source_path"]]
            claim["source_provenance"] = provenance(source_by_entity[claim["source_entity"]])
            origins.append(claim["source_provenance"])
        # Candidate classification uses captured endpoint presence and Wikidata
        # type statements, independently of the identifier assertions themselves.
        # Bind those sources too: an unchanged ROR link can change classification
        # when the captured Wikidata source changes.
        decision_inputs = []
        for endpoint in (candidate["ror"], candidate["wikidata"]):
            source = source_by_entity.get(endpoint)
            if source is None:
                continue
            spec = source["spec"]
            prefix = "" if spec["provider"] == "ror" else "/entities/" + spec["entity_id"]
            origin = provenance(source)
            origins.append(origin)
            decision_inputs.append({"role": "captured_endpoint", "source_entity": endpoint,
                "source_path": prefix, "evidence_id": address_ids[endpoint, prefix or "/"],
                "source_provenance": origin})
            if spec["provider"] == "wikidata":
                for index, statement in enumerate(source["entity"].get("claims", {}).get("P31", [])):
                    pointer = prefix + f"/claims/P31/{index}"
                    decision_inputs.append({"role": "wikidata_type_check", "source_entity": endpoint,
                        "source_path": pointer, "evidence_id": address_ids[endpoint, pointer],
                        "admissibility_reasons": legacy.statement_reasons(statement), "source_provenance": origin})
        candidate["decision_inputs"] = decision_inputs
        origins = [json.loads(raw) for raw in sorted({encoded(item) for item in origins})]
        eid = "crosswalk-" + hashlib.sha256(encoded([candidate["ror"], candidate["wikidata"], origins])).hexdigest()[:20]
        candidate["candidate_evidence_id"] = eid
        mentions = {entity for entity in (candidate["ror"], candidate["wikidata"]) if entity in node_by_id}
        add_record(eid, "crosswalk", mentions, candidate["ror"] + " / " + candidate["wikidata"] + " — identity candidate",
                   min(item["retrieved_at_utc"][:10] for item in origins), {"candidate": copy.deepcopy(candidate)}, origins)

    proofs = {}
    for decision in ledger["decisions"]:
        if "projected_edge" in decision:
            proofs.setdefault(tuple(decision["projected_edge"]), set()).add(decision["evidence_id"])
    for edge in graph["edges"]:
        edge["evidence_ids"] = sorted(proofs[edge["source"], edge["target"]])
    for decision in ledger["decisions"]:
        if decision.get("evidence_id") and decision["evidence_id"] not in seen:
            raise ProjectionError("projection_points_to_missing_source_unit")
    manifest.sort(key=lambda item: item["id"])
    files["graph.json"] = encoded(graph)
    files["manifest.json"] = encoded(manifest)
    files["projection-ledger.json"] = encoded(ledger)
    files["dataset.json"] = encoded({"id": "public-research-statement-pilot", "name": "Captured ROR/Wikidata source units",
        "kind": "public_snapshot", "version": VERSION, "license": "CC0 structured data; linked media excluded",
        "description": "Complete individually addressable selected statements, relationships and identity candidates. " + legacy.CAUTION})
    returned = [{**entry, "source": entry["path"], "text": files[entry["path"]].decode("utf-8"),
                 "sha256": capture.digest(files[entry["path"]])} for entry in manifest]
    sizes = [(len(json.dumps(record, ensure_ascii=False).encode("utf-8")), record["id"]) for record in returned]
    totals = {**prior_totals, "indexed_evidence_records": len(manifest), "record_types": dict(sorted(role_counts.items())),
              "wikidata_statements_indexed": role_counts["statement"],
              "indexed_evidence_file_bytes": sum(len(files[item["path"]]) for item in manifest),
              "largest_returned_record_bytes": max(sizes)[0], "largest_returned_record_id": max(sizes)[1],
              "all_records_json_bytes": len(json.dumps(returned, ensure_ascii=False).encode("utf-8")),
              "output_bytes_excluding_import_manifest": sum(map(len, files.values()))}
    policy = {"network": "none", "identity_merging": "none", "indexed_wikidata_properties": sorted(legacy.INDEXED_PROPERTIES),
        "projection": "Unchanged conservative legacy policy; edge proofs reference exact source units. Qualified claims remain literal evidence.",
        "identity_fields": "All ROR fields except separately indexed relationships/external_ids; Wikidata id/type/lastrevid/modified/labels/aliases/descriptions when present.",
        "ror_records": "Every relationship and every external-ID group, with every field preserved.",
        "statement_records": "Every statement of each selected property; every field/qualifier/reference preserved. No maximum subset or truncation.",
        "unindexed_coverage": "All source bytes preserved; other properties remain raw-only and are not automatically accessible to model tools.",
        "assertions": "Empty simplified triples; compound/qualified source claims are not flattened.",
        "date_semantics": "Source units use capture date. Derived crosswalk records use earliest contributing capture date, never assertion validity.",
        "retrieval": "Existing search still returns full records. Bounded catalog/selective-read integration remains pending.",
        "maximum_returned_record_bytes": MAX_RECORD_BYTES, "maximum_output_bytes": MAX_OUTPUT_BYTES,
        "size_measurement": "UTF-8 json.dumps(ensure_ascii=False) with default separators, excluding MCP envelopes."}
    files["import-manifest.json"] = encoded({"schema_version": 1, "projection_version": VERSION, "totals": totals,
        "capture_manifest_sha256": capture.digest(capture_bytes), "builder_sha256": capture.digest(Path(__file__).read_bytes()),
        "legacy_importer_sha256": capture.digest(Path(legacy.__file__).read_bytes()), "policy": policy,
        "files": [{"path": path, "sha256": capture.digest(raw), "size_bytes": len(raw)} for path, raw in sorted(files.items())]})
    if sum(map(len, files.values())) > MAX_OUTPUT_BYTES:
        raise ProjectionError("statement_dataset_exceeds_output_byte_limit")
    return files, totals


def import_dataset(capture_dir: Path, output_dir: Path | None = None):
    """Verify first; only a fresh destination may be published. The old import is untouched."""
    if output_dir is not None and (output_dir.exists() or output_dir.is_symlink()):
        raise ProjectionError("output_exists_refusing_overwrite")
    sources, capture_bytes = legacy.load_sources(capture_dir)
    files, totals = build_dataset(sources, capture_bytes)
    if output_dir is None:
        return totals
    # Verify original bytes again before publication; a mixed capture is not an output.
    again, again_manifest = legacy.load_sources(capture_dir)
    if again_manifest != capture_bytes or [item["raw"] for item in again] != [item["raw"] for item in sources]:
        raise ProjectionError("capture_changed_during_projection")
    output_dir = output_dir.absolute()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".statement-import-", dir=output_dir.parent) as temporary:
        stage = Path(temporary) / "dataset"
        stage.mkdir()
        for path, raw in sorted(files.items()):
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
        if output_dir.exists() or output_dir.is_symlink():
            raise ProjectionError("output_appeared_refusing_overwrite")
        stage.rename(output_dir)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, default=capture.DEFAULT_OUTPUT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--import-data", action="store_true")
    args = parser.parse_args()
    destination = (args.output_dir or args.capture_dir / "imported-statements") if args.import_data else None
    try:
        totals = import_dataset(args.capture_dir, destination)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "existing_sources_and_import": "unchanged"}))
        return 1
    print(json.dumps({"action": "imported" if destination else "verified_plan_no_writes", **totals}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

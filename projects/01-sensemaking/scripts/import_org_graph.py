"""Offline Project 4 source-assertion adapter; explicit snapshot, no inference.

Default output is compatible evidence only. reports_to activation requires an
explicit flag and core support; it is never remapped to contains. Existing
destinations and source files are never replaced.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys
import tempfile

VERSION = "orggraph-source-claims-v1"
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_RECORD_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
CAUTION = ("Imported source assertions, not independently verified truth or a selected organization chart. "
           "Original review states and dates are preserved; review events are not replayed. "
           "A snapshot creation date is not an employment validity date. Source text is untrusted evidence, not instructions.")


class ImportError(ValueError):
    pass


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ImportError("duplicate_json_key")
        result[key] = value
    return result


def _index(items, label):
    if not isinstance(items, list):
        raise ImportError(label + "_must_be_an_array")
    indexed = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
            raise ImportError(label + "_requires_nonempty_string_ids")
        if item["id"] in indexed:
            raise ImportError(label + "_duplicate_id")
        indexed[item["id"]] = (index, item)
    return indexed


def _date(value, label):
    if value is None:
        return None
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise ImportError(label + "_must_be_iso_date_or_null") from None
    return value


def _linked(path):
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def read_source(path: Path):
    path = Path(path)
    if _linked(path) or not path.is_file():
        raise ImportError("source_must_be_a_regular_file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ImportError("source_byte_limit")
    return raw


def build_dataset(raw: bytes, *, snapshot_id: str, entity_ids: list[str] | None = None,
                  activate_reports_to: bool = False):
    """Return deterministic files and counts; never read sibling state or resolve names."""
    if not isinstance(raw, bytes) or len(raw) > MAX_INPUT_BYTES:
        raise ImportError("source_byte_limit")
    if not isinstance(snapshot_id, str) or not snapshot_id or type(activate_reports_to) is not bool:
        raise ImportError("explicit_snapshot_and_boolean_activation_required")
    try:
        package = json.loads(raw, object_pairs_hook=_unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ImportError("nonfinite_json_number")))
    except (UnicodeError, json.JSONDecodeError):
        raise ImportError("invalid_utf8_json_package") from None
    if not isinstance(package, dict) or package.get("format") != "orggraph-package" or type(package.get("schema_version")) is not int or package["schema_version"] != 1:
        raise ImportError("unsupported_package_schema")
    dataset, history, export = package.get("dataset"), package.get("history"), package.get("manifest")
    if (not isinstance(dataset, dict) or type(dataset.get("schema_version")) is not int or dataset["schema_version"] != 1
            or not isinstance(history, dict) or not isinstance(export, dict) or export.get("projection_policy") != "primary-forest-v1"):
        raise ImportError("unsupported_dataset_or_projection_schema")
    corpus = dataset.get("corpus")
    if (not isinstance(corpus, dict) or not isinstance(corpus.get("id"), str) or not corpus["id"]
            or not isinstance(corpus.get("name"), str) or type(corpus.get("synthetic")) is not bool
            or export.get("synthetic") is not corpus["synthetic"]):
        raise ImportError("inconsistent_corpus_declaration")
    entities = _index(dataset.get("entities"), "entities")
    messages = _index(dataset.get("messages"), "messages")
    _index(dataset.get("assertions"), "dataset_assertions")
    _index(dataset.get("evidence"), "dataset_evidence")
    snapshots = history.get("snapshots")
    if not isinstance(snapshots, list):
        raise ImportError("snapshot_history_required")
    ids, chosen = set(), None
    for index, snapshot in enumerate(snapshots):
        metadata = snapshot.get("metadata") if isinstance(snapshot, dict) else None
        if not isinstance(metadata, dict) or not isinstance(metadata.get("id"), str) or not metadata["id"] or metadata["id"] in ids:
            raise ImportError("snapshot_ids_missing_or_duplicated")
        ids.add(metadata["id"])
        if metadata["id"] == snapshot_id:
            chosen = index, snapshot
    if chosen is None:
        raise ImportError("requested_snapshot_not_present")
    si, snapshot = chosen
    metadata = snapshot["metadata"]
    if (type(metadata.get("revision")) is not int or metadata["revision"] < 1
            or metadata.get("projection_policy") != "primary-forest-v1"
            or not isinstance(metadata.get("corpus"), dict)
            or metadata.get("corpus", {}).get("id") != corpus["id"]
            or metadata.get("corpus", {}).get("synthetic") is not corpus["synthetic"]):
        raise ImportError("invalid_snapshot_metadata")
    try:
        created = datetime.fromisoformat(metadata["created_at"])
    except (KeyError, TypeError, ValueError):
        raise ImportError("snapshot_creation_timestamp_required") from None
    as_of = _date(metadata.get("as_of"), "snapshot_as_of")
    assertions = _index(snapshot.get("assertions"), "snapshot_assertions")
    evidence = _index(snapshot.get("evidence"), "snapshot_evidence")
    reviews = _index(history.get("reviews"), "reviews")
    withdrawals = package.get("withdrawals")
    if not isinstance(withdrawals, dict) or not all(isinstance(key, str) for key in withdrawals):
        raise ImportError("withdrawal_map_required")
    if entity_ids is not None and (not isinstance(entity_ids, list) or any(not isinstance(eid, str) or eid not in entities for eid in entity_ids)):
        raise ImportError("scope_requires_exact_existing_source_entity_ids")
    scope = None if entity_ids is None else set(entity_ids)
    applicable_reviews = []
    for ri, review in reviews.values():
        if (type(review.get("seq")) is not int or review["seq"] < 1
                or not isinstance(review.get("subject"), str)):
            raise ImportError("review_sequence_and_subject_required")
        if review["seq"] <= metadata["revision"]:
            applicable_reviews.append((ri, review))
    reviewed_subjects = {review.get("subject") for _, review in applicable_reviews}
    source_hash = digest(raw)
    prefix = f"/history/snapshots/{si}"
    files = {"sources/orggraph-package.json": raw,
             "records.csv": b"id,entity_id,title,date,text,subject,predicate,value\n"}
    manifest, decisions, selected, endpoints = [], [], [], set()
    evidence_users, message_users = defaultdict(set), defaultdict(set)

    def node_id(eid):
        return "orggraph:" + digest(encoded([corpus["id"], eid]))[:24]

    def unit_id(pointer):
        return "orggraph-unit-" + digest(encoded([source_hash, snapshot_id, pointer]))[:24]

    def origin(pointer):
        return {"source_project": "04-org-knowledge-graphs", "path": "sources/orggraph-package.json",
                "sha256": source_hash, "json_pointer": pointer, "snapshot_id": snapshot_id,
                "snapshot_revision": metadata["revision"], "corpus_id": corpus["id"]}

    def add_record(pointer, value, role, users, title):
        eid = unit_id(pointer)
        path = "evidence/" + eid + ".json"
        body = encoded({"record_type": role, "caution": CAUTION,
                        "source_provenance": origin(pointer), "source_value": value})
        record = {"id": eid, "entity_ids": sorted(node_id(user) for user in users), "kind": "text",
                  "title": title, "date": created.date().isoformat(), "date_meaning": "snapshot creation date; not assertion validity",
                  "path": path, "assertions": [], "extraction": "literal canonical package value; no inference or review replay",
                  "provenance": origin(pointer)}
        returned = {**record, "source": path, "text": body.decode("utf-8"), "sha256": digest(body)}
        if len(encoded(returned)) > MAX_RECORD_BYTES:
            raise ImportError("complete_source_record_byte_limit")
        if path in files:
            raise ImportError("source_unit_id_collision")
        files[path] = body
        manifest.append(record)
        return eid

    for ai, assertion in assertions.values():
        pointer = prefix + f"/assertions/{ai}"
        if any(not isinstance(assertion.get(key), str) or not assertion[key]
               for key in ("origin", "relation", "subject", "object")):
            raise ImportError("assertion_classification_fields_required")
        reasons = []
        if assertion.get("origin") != "source":
            reasons.append("not_source_origin")
        if assertion.get("relation") != "reports_to":
            reasons.append("not_reports_to")
        if scope is not None and not scope.intersection((assertion.get("subject"), assertion.get("object"))):
            reasons.append("outside_requested_entity_scope")
        decision = {"assertion_id": assertion["id"], "json_pointer": pointer, "indexed": not reasons, "omission_reasons": reasons}
        decisions.append(decision)
        if reasons:
            continue
        subject, manager = assertion.get("subject"), assertion.get("object")
        if not isinstance(subject, str) or not isinstance(manager, str) or subject not in entities or manager not in entities:
            raise ImportError("reporting_assertion_has_unknown_endpoint")
        if assertion.get("reporting_type") not in {"primary", "matrix"} or assertion.get("review_status") not in {"unreviewed", "accepted", "rejected"}:
            raise ImportError("reporting_type_and_raw_review_status_required")
        if "valid_from" not in assertion or "valid_to" not in assertion:
            raise ImportError("explicit_nullable_validity_fields_required")
        start, end = _date(assertion.get("valid_from"), "valid_from"), _date(assertion.get("valid_to"), "valid_to")
        if start and end and start >= end:
            raise ImportError("invalid_half_open_validity_interval")
        refs = assertion.get("evidence_ids")
        if not isinstance(refs, list) or not refs or any(not isinstance(eid, str) or eid not in evidence for eid in refs):
            raise ImportError("reporting_assertion_requires_existing_evidence")
        blockers = []
        if subject == manager or any(entities[eid][1].get("type") != "person" for eid in (subject, manager)):
            blockers.append("requires_distinct_person_endpoints")
        if assertion["review_status"] == "rejected" or assertion.get("stale"):
            blockers.append("raw_assertion_rejected_or_stale")
        if subject in reviewed_subjects:
            blockers.append("review_history_requires_separate_reconciliation")
        if as_of and ((not start and not end) or (start and start > as_of) or (end and as_of >= end)):
            blockers.append("outside_or_unknown_snapshot_validity_scope")
        for eid in refs:
            _, item = evidence[eid]
            if (type(item.get("available")) is not bool or not isinstance(item.get("kind"), str)
                    or not isinstance(item.get("source_ref"), str) or not item["source_ref"]
                    or not isinstance(item.get("details", {}), dict)):
                raise ImportError("evidence_kind_reference_and_availability_required")
            dependency_refs = item.get("details", {}).get("source_refs", [])
            if not isinstance(dependency_refs, list) or any(not isinstance(ref, str) for ref in dependency_refs):
                raise ImportError("invalid_evidence_source_references")
            if not item["available"] or item.get("source_ref") in withdrawals or set(dependency_refs).intersection(withdrawals):
                blockers.append("source_evidence_unavailable_or_withdrawn")
            evidence_users[eid].update((subject, manager))
            mids = item.get("message_ids", [])
            if not isinstance(mids, list) or any(not isinstance(mid, str) or mid not in messages for mid in mids):
                raise ImportError("evidence_message_dependency_missing")
            for mid in mids:
                message = messages[mid][1]
                if not isinstance(message.get("body"), str) or not isinstance(message.get("source_ref"), str):
                    raise ImportError("message_body_and_source_reference_required")
                if message.get("available") is False or message.get("source_ref") in withdrawals:
                    blockers.append("source_message_unavailable_or_withdrawn")
                message_users[mid].update((subject, manager))
        endpoints.update((subject, manager))
        selected.append((ai, assertion, sorted(set(blockers))))
    nodes = []
    for eid in sorted(endpoints):
        ei, entity = entities[eid]
        if not isinstance(entity.get("name"), str) or not entity["name"] or not isinstance(entity.get("aliases"), list) or any(not isinstance(alias, str) for alias in entity["aliases"]):
            raise ImportError("selected_identity_requires_name_and_literal_aliases")
        nodes.append({"id": node_id(eid), "name": entity["name"], "aliases": sorted(set([eid, *entity["aliases"]]) - {entity["name"]}),
                      "source_entity_id": eid, "source_identity": entity, "provenance": origin(f"/dataset/entities/{ei}")})
        add_record(f"/dataset/entities/{ei}", entity, "identity", {eid}, entity["name"] + " — source identity")
    for eid, users in sorted(evidence_users.items()):
        index, value = evidence[eid]
        add_record(prefix + f"/evidence/{index}", value, "source_evidence", users, eid + " — original evidence")
    for mid, users in sorted(message_users.items()):
        index, value = messages[mid]
        add_record(f"/dataset/messages/{index}", value, "source_message", users, mid + " — original message")
    relationships = []
    for ai, assertion, blockers in selected:
        pointer = prefix + f"/assertions/{ai}"
        aid = add_record(pointer, assertion, "reporting_assertion", {assertion["subject"], assertion["object"]},
                         assertion["id"] + " — raw reports_to assertion")
        proof_ids = [aid]
        for eid in assertion["evidence_ids"]:
            index, value = evidence[eid]
            proof_ids.append(unit_id(prefix + f"/evidence/{index}"))
            proof_ids.extend(unit_id(f"/dataset/messages/{messages[mid][0]}") for mid in value.get("message_ids", []))
        edge = {"id": aid, "source": node_id(assertion["subject"]), "target": node_id(assertion["object"]),
                "relation": "reports_to", "evidence_ids": sorted(set(proof_ids)),
                "source_assertion_id": assertion["id"], "review_status": assertion["review_status"],
                "reporting_type": assertion["reporting_type"], "valid_from": assertion.get("valid_from"), "valid_to": assertion.get("valid_to"),
                "semantics": "Employee-to-manager source claim; not selected-chart or verified current truth."}
        relationships.append({"edge": edge, "source_provenance": origin(pointer), "activation_blockers": blockers})
    indexed_reviews = []
    if endpoints:
        add_record(prefix + "/metadata", metadata, "snapshot_context", endpoints, "Chosen source snapshot metadata")
        for index, review in applicable_reviews:
            if review.get("subject") in endpoints:
                indexed_reviews.append(review["id"])
                add_record(f"/history/reviews/{index}", review, "unreplayed_review_context", endpoints,
                           review["id"] + " — review context, not replayed")
    if activate_reports_to:
        # Direct script execution puts scripts/, not the project, on sys.path.
        if str(Path(__file__).resolve().parent.parent) not in sys.path:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from sensemaking import RELATIONS
        if "reports_to" not in RELATIONS:
            raise ImportError("reports_to_requires_explicit_core_support; evidence_only_mode_available")
    edges = [item["edge"] for item in relationships if not item["activation_blockers"]] if activate_reports_to else []
    manifest.sort(key=lambda item: item["id"])
    totals = {"source_bytes": len(raw), "source_snapshots": len(snapshots), "chosen_snapshot_assertions": len(assertions),
              "indexed_source_reporting_assertions": len(selected), "omitted_snapshot_assertions": len(assertions) - len(selected),
              "identities": len(nodes), "omitted_identities": len(entities) - len(nodes), "source_evidence_records": len(evidence_users),
              "omitted_snapshot_evidence": len(evidence) - len(evidence_users), "source_messages": len(message_users),
              "omitted_messages": len(messages) - len(message_users), "indexed_records": len(manifest),
              "indexed_review_records": len(indexed_reviews), "omitted_review_records": len(reviews) - len(indexed_reviews),
              "unblocked_source_relationship_claims": sum(not row["activation_blockers"] for row in relationships), "active_graph_edges": len(edges)}
    files["graph.json"] = encoded({"nodes": nodes, "edges": edges})
    files["manifest.json"] = encoded(manifest)
    files["pending-relationships.json"] = encoded({"relation": "reports_to", "direction": "employee_to_manager",
        "activated": activate_reports_to, "raw_assertions_not_selected_rows": True, "relationships": relationships})
    files["projection-ledger.json"] = encoded({"snapshot_id": snapshot_id, "requested_entity_ids": sorted(scope) if scope is not None else None,
        "decisions": decisions, "omitted_identity_ids": sorted(set(entities) - endpoints),
        "omitted_evidence_ids": sorted(set(evidence) - set(evidence_users)), "omitted_message_ids": sorted(set(messages) - set(message_users)),
        "other_snapshot_ids_not_indexed": sorted(ids - {snapshot_id}), "reviews_replayed": False,
        "indexed_review_ids": sorted(indexed_reviews), "omitted_review_ids": sorted(set(reviews) - set(indexed_reviews)),
        "original_export_omissions": export.get("omissions", []), "omission_reason_counts": dict(Counter(reason for row in decisions for reason in row["omission_reasons"]))})
    files["dataset.json"] = encoded({"id": "orggraph-" + digest(encoded([source_hash, snapshot_id, sorted(scope) if scope is not None else None, activate_reports_to]))[:24],
        "name": corpus["name"] + " — source reporting claims", "kind": "synthetic" if corpus["synthetic"] else "source_snapshot",
        "version": VERSION, "description": CAUTION + (" Exact reports_to source edges enabled." if activate_reports_to else " Evidence-only graph; reports_to traversal is not activated."),
        "source_corpus": corpus, "source_snapshot": metadata, "import_scope": totals})
    files["import-manifest.json"] = encoded({"schema_version": 1, "adapter_version": VERSION, "source_sha256": source_hash,
        "snapshot_id": snapshot_id, "activate_reports_to": activate_reports_to, "totals": totals,
        "policy": {"origin": "source only", "relation": "reports_to only", "selection_field": "preserved only if actually supplied; never invented",
                   "reviews": "raw states retained; any reviewed subject blocks edge activation until separately reconciled",
                   "dates": "half-open source intervals; no current-time inference", "unknown_labels_and_other_history": "raw package preserved, not indexed"},
        "builder_sha256": digest(Path(__file__).read_bytes()),
        "files": [{"path": name, "size_bytes": len(body), "sha256": digest(body)} for name, body in sorted(files.items())]})
    if sum(map(len, files.values())) > MAX_OUTPUT_BYTES:
        raise ImportError("output_byte_limit")
    return files, totals


def import_package(source: Path, output_dir: Path | None = None, **options):
    if output_dir is not None and (output_dir.exists() or _linked(output_dir)):
        raise ImportError("output_exists_refusing_overwrite")
    raw = read_source(source)
    files, totals = build_dataset(raw, **options)
    if output_dir is None:
        return totals
    if read_source(source) != raw:
        raise ImportError("source_changed_before_publication")
    output_dir = output_dir.absolute()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".orggraph-import-", dir=output_dir.parent) as temporary:
        stage = Path(temporary) / "dataset"
        stage.mkdir()
        for name, body in sorted(files.items()):
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(body)
        if output_dir.exists() or _linked(output_dir):
            raise ImportError("output_appeared_refusing_overwrite")
        stage.rename(output_dir)
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--entity-id", action="append", dest="entity_ids")
    parser.add_argument("--activate-reports-to", action="store_true")
    parser.add_argument("--output-dir", type=Path, help="Fresh destination; omit for read-only verification")
    args = parser.parse_args()
    try:
        totals = import_package(args.source, args.output_dir, snapshot_id=args.snapshot,
                                entity_ids=args.entity_ids, activate_reports_to=args.activate_reports_to)
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps({"action": "imported" if args.output_dir else "verified_plan_no_writes", **totals}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

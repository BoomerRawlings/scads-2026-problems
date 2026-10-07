"""Package an explicit allowlist into a static, read-only saved-case showcase.

No network, third-party package, live inference, deployment or directory deletion.
--refresh replaces only unchanged files owned by a previous successful build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
SHOWCASE = PROJECT / "showcase"
sys.path.insert(0, str(PROJECT))
from sensemaking import Workspace

OWNER = "scads-sensemaking-static-showcase-v1"
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
TEXT_EXTENSIONS = {".json", ".md", ".txt", ".csv", ".html", ".css", ".js"}
PUBLIC_METADATA = {"engine", "model", "started_at", "elapsed_seconds", "steps", "question", "requested_target", "status",
                   "report_rejections", "intent_rejections", "invalid_actions", "temperature", "seed", "prompt_sha256", "retrieval_profile"}
DOCUMENTS = ["docs/decisions.md", "docs/acceptance.md", "docs/local-validation.md", "docs/integration.md", "docs/scaling.md",
             "evaluations/local-pilot/REVIEW-PROTOCOL.md", "evaluations/local-pilot/implementation-v6/snapshot.json",
             "showcase/README.md", "showcase/QA.md"]
DATASETS = {
    "cedar-basin-synthetic-v1": {"root": "data", "kind": "synthetic",
        "review_protocol": "evaluations/local-pilot/REVIEW-PROTOCOL.md",
        "note": "Authored synthetic fixture. Caption media repeats fixture text and is not independent corroboration."},
    "public-research-statement-pilot": {"root": "datasets/public-research/imported-statements", "kind": "public_snapshot",
        "review_protocol": "evaluations/public-pilot/PROTOCOL.md",
        "note": "Captured ROR/Wikidata source assertions, not independently verified current facts. Dates describe capture or registry edits, not relationship validity. Candidate identifiers do not merge identities. Linked media was not imported."},
}
# These pre-fingerprint artifacts predate dataset metadata. No new case may silently omit it.
LEGACY_UNBOUND_CASES = {"cbri", "ambiguous-delta"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def linked(path):
    if path.is_symlink():
        return True
    try:
        return getattr(path.lstat(), "st_reparse_tag", None) == 0xA0000003  # Windows directory junction, including Python 3.11.
    except FileNotFoundError:
        return False


def reject_linked_components(path):
    """Keep the lexical path until every existing ancestor has been checked."""
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if linked(current):
            raise ValueError("Linked path component rejected")
    return absolute


def safe_read(root, relative, scan_text=True):
    relative = Path(relative)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("Package source must use a contained relative path")
    root = reject_linked_components(root)
    path = reject_linked_components(root / relative)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Linked or escaping package source rejected")
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Package source missing or oversized: " + relative.as_posix())
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Package source grew beyond byte limit: " + relative.as_posix())
    if scan_text and path.suffix in TEXT_EXTENSIONS:
        text = raw.decode("utf-8")
        if re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", text) or "\\\\Users\\" in text or "/Users/" in text or "/home/" in text:
            raise ValueError("Machine-specific path found in public artifact: " + relative.as_posix())
    return raw


def grounded_observation_artifacts(metadata, report, trace, read_output):
    """Publish only successful observation lineage; preserve/verify original output bytes."""
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate isolated observation JSON key")
            value[key] = item
        return value

    grounding = metadata.get("grounded_media")
    if not isinstance(grounding, dict) or grounding.get("enabled") is not True:
        return None, {}
    if grounding.get("policy") != "deferred-isolated-pixels-v1":
        raise ValueError("Unsupported grounded-media artifact policy")
    constrained = grounding.get("constrained_fields")
    allowed_fields = {"media_observations", "limitations", "follow_up"}
    summary_metadata = evidence_summary_metadata(metadata, report)
    summary_fixed = summary_metadata and summary_metadata["final_summary_constrained"]
    if summary_fixed:
        allowed_fields.add("summary")
    if (not isinstance(constrained, list) or any(not isinstance(field, str) for field in constrained)
            or len(constrained) != len(set(constrained)) or not {"media_observations", "limitations"}.issubset(constrained)
            or set(constrained) - allowed_fields or (summary_fixed and "summary" not in constrained)):
        raise ValueError("Grounded case lacks supported constrained fields")
    if "follow_up" in constrained and report.get("follow_up") != []:
        raise ValueError("Grounded synthetic follow-up is not the recorded empty policy")
    records = grounding.get("observations")
    if not isinstance(records, list):
        raise ValueError("Grounded observation lineage missing")
    outputs, published, observations, seen_calls = {}, [], [], set()
    successful_media_calls = {index for index, call in enumerate(trace, 1)
                              if call.get("name") == "read_media" and call.get("status") == "completed"}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Invalid grounded observation record")
        if record.get("status") != "observed":
            continue  # Failed/running outputs and reasons are deliberately not published.
        number, evidence_id, locators, path = [record.get(key) for key in ("call", "evidence_id", "locators", "path")]
        if (isinstance(number, bool) or not isinstance(number, int) or number not in successful_media_calls
                or number in seen_calls or not isinstance(evidence_id, str)
                or trace[number - 1].get("args", {}).get("evidence_id") != evidence_id):
            raise ValueError("Observation is not linked to a unique successful read_media call")
        if (not isinstance(locators, list) or not locators or any(not isinstance(locator, str)
                or (locator != "image" and not re.fullmatch(r"(?:[0-9]{2}:)?[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?", locator)) for locator in locators)
                or not isinstance(path, str) or not re.fullmatch(r"media-observation-[0-9]{2,}\.json", path)
                or path in outputs):
            raise ValueError("Invalid observation path or recorded locators")
        for key in ("input_sha256", "output_sha256"):
            if not isinstance(record.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", record[key]):
                raise ValueError("Invalid observation fingerprint")
        raw = read_output(path)
        if digest(raw) != record["output_sha256"]:
            raise ValueError("Isolated observation output hash mismatch")
        output = json.loads(raw, object_pairs_hook=unique_object)
        items = output.get("media_observations") if isinstance(output, dict) else None
        if (not isinstance(output, dict) or set(output) != {"media_observations"}
                or not isinstance(items, list) or len(items) != len(locators)):
            raise ValueError("Unexpected isolated observation output fields")
        for item, locator in zip(items, locators):
            if (not isinstance(item, dict) or set(item) != {"evidence_id", "locator", "observation"}
                    or item.get("evidence_id") != evidence_id or item.get("locator") != locator
                    or not isinstance(item.get("observation"), str) or not item["observation"].strip()):
                raise ValueError("Isolated observation source/locator order mismatch")
        outputs[path] = raw
        observations.extend(items)
        seen_calls.add(number)
        published.append({key: record[key] for key in ("call", "evidence_id", "locators", "path", "input_sha256", "output_sha256", "status")})
    if seen_calls != successful_media_calls:
        raise ValueError("Successful media calls lack isolated observation records")
    if report.get("media_observations") != observations:
        raise ValueError("Final report changed or reordered isolated observations")
    return {"enabled": True, "policy": grounding["policy"], "constrained_fields": constrained,
            "observations": published, "output_hashes_verified": True, "final_observations_match": True}, outputs


def compact_synthesis_summary(metadata):
    """Expose recorded construction metrics, never source/context bodies or settings."""
    compact = metadata.get("compact_synthesis")
    if not isinstance(compact, dict) or compact.get("enabled") is not True:
        return None
    generations = compact.get("generations")
    if not isinstance(generations, list) or not generations:
        raise ValueError("Compact synthesis lacks recorded report generations")
    count_keys = ("mcp_calls", "evidence_occurrences", "omitted_raw_image_blocks", "evidence_records",
                  "duplicate_evidence_records", "identity_graph_results", "tool_failures")
    published = []
    for generation in generations:
        if (not isinstance(generation, dict) or generation.get("policy") != "exact-record-compact-synthesis-v1"
                or generation.get("input_scope") != "canonical_report_messages_only"):
            raise ValueError("Unsupported compact synthesis construction policy or hash scope")
        for key in ("step", "input_bytes"):
            if type(generation.get(key)) is not int or generation[key] <= 0:
                raise ValueError("Invalid compact synthesis recorded metric")
        fingerprint = generation.get("input_sha256")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("Invalid compact synthesis recorded fingerprint")
        counts = generation.get("counts")
        if not isinstance(counts, dict) or any(type(counts.get(key)) is not int or counts[key] < 0 for key in count_keys):
            raise ValueError("Invalid compact synthesis recorded counts")
        if counts["evidence_occurrences"] != counts["evidence_records"] + counts["duplicate_evidence_records"]:
            raise ValueError("Inconsistent compact synthesis recorded counts")
        item = {key: generation[key] for key in ("step", "policy", "input_scope", "input_sha256", "input_bytes")}
        item["counts"] = {key: counts[key] for key in count_keys}
        published.append(item)
    return {"enabled": True, "generations": published}


def evidence_summary_metadata(metadata, report):
    """Expose recorded host construction; verify only the final summary's byte identity."""
    construction = metadata.get("evidence_summary")
    if not isinstance(construction, dict) or construction.get("enabled") is not True:
        return None
    if (construction.get("policy") != "exact-assertion-evidence-overview-v1"
            or construction.get("scope") != "complete_reports_only"):
        raise ValueError("Unsupported evidence-summary construction policy")
    generations = construction.get("generations")
    if not isinstance(generations, list):
        raise ValueError("Evidence summary lacks recorded generations")
    count_keys = ("source_ids", "record_versions", "comparable_assertions", "ignored_assertions",
                  "records_without_assertions", "differing_groups")
    published = []
    for generation in generations:
        if (not isinstance(generation, dict) or generation.get("status") != "complete"
                or generation.get("attribution") != "host_constructed"):
            raise ValueError("Invalid evidence-summary attribution or intended status")
        for key in ("step", "summary_bytes"):
            if type(generation.get(key)) is not int or generation[key] <= 0:
                raise ValueError("Invalid evidence-summary recorded metric")
        checksum = generation.get("summary_sha256")
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("Invalid evidence-summary recorded fingerprint")
        counts = generation.get("counts")
        if not isinstance(counts, dict) or any(type(counts.get(key)) is not int or counts[key] < 0 for key in count_keys):
            raise ValueError("Invalid evidence-summary recorded counts")
        item = {key: generation[key] for key in ("step", "status", "attribution", "summary_sha256", "summary_bytes")}
        item["counts"] = {key: counts[key] for key in count_keys}
        published.append(item)
    final_fixed = report.get("status") == "complete"
    if final_fixed:
        if not published or not isinstance(report.get("summary"), str):
            raise ValueError("Complete evidence-summary report lacks construction record")
        raw = report["summary"].encode("utf-8")
        if len(raw) != published[-1]["summary_bytes"] or digest(raw) != published[-1]["summary_sha256"]:
            raise ValueError("Final report summary differs from recorded host construction")
    return {"enabled": True, "policy": construction["policy"], "scope": construction["scope"],
            "generations": published, "final_summary_constrained": final_fixed,
            "final_summary_hash_verified": final_fixed}


def load_dataset(project, dataset_id, include, files):
    """Preflight a named dataset; verify public projection before parsing source text."""
    if dataset_id not in DATASETS:
        raise ValueError("Dataset outside explicit showcase allowlist")
    definition = DATASETS[dataset_id]
    root = definition["root"]
    inputs = set()

    def source(relative):
        path = Path(relative)
        if path.is_absolute() or path.drive or ".." in path.parts or "\\" in relative:
            raise ValueError("Dataset source must use a contained relative path")
        inputs.add(relative)
        return include(root + "/" + relative)

    for name in ("records.csv", "graph.json", "manifest.json", "dataset.json"):
        source(name)
    descriptor = json.loads(files["artifacts/" + root + "/dataset.json"])
    if descriptor.get("id") != dataset_id or descriptor.get("kind") != definition["kind"]:
        raise ValueError("Dataset descriptor differs from configured identity/kind")
    manifest = json.loads(files["artifacts/" + root + "/manifest.json"])
    indexed = set(inputs)
    for item in manifest:
        for field in ("path", "media_path"):
            if item.get(field):
                source(item[field])
                indexed.add(item[field])
    if definition["kind"] == "public_snapshot":
        from scripts import import_public_statements as projection

        # Exact fixed capture paths, not arbitrary manifest paths or linked URLs.
        source("sources/capture-manifest.json")
        for spec in projection.capture.SOURCES:
            source("sources/" + projection.capture.raw_path(spec))
        sources, capture_bytes = projection.legacy.load_sources(project / root / "sources")
        expected, _ = projection.build_dataset(sources, capture_bytes)
        for name, raw in expected.items():
            path = source(name)
            if files[path] != raw:
                raise ValueError("Public dataset differs from verified offline reproduction: " + name)
        include("docs/public-statements.md")
        include("docs/evidence-catalog.md")
    protocol_url = include(definition["review_protocol"])
    hashes = {name: digest(files["artifacts/" + root + "/" + name]) for name in sorted(indexed)}
    fingerprint = digest(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    workspace = Workspace(project / root)
    try:
        evidence = {item["id"]: dict(item) for item in workspace.search()}
    finally:
        workspace.close()
    for item in evidence.values():
        locator = item["source"].split("#", 1)[0]
        if locator not in indexed:
            raise ValueError("Indexed source locator was not preflighted")
        item["file_url"] = "artifacts/" + root + "/" + locator
        item["file_locator"] = item["source"]
        if item.get("media_path"):
            media = item["media_path"]
            if media not in indexed:
                raise ValueError("Indexed media was not preflighted")
            item["media_url"] = "artifacts/" + root + "/" + media
            item["current_media_sha256"] = digest(files[item["media_url"]])
    for name in inputs:
        if safe_read(project, root + "/" + name) != files["artifacts/" + root + "/" + name]:
            raise ValueError("Dataset changed during showcase construction")
    return {"id": dataset_id, "name": descriptor.get("name", dataset_id), "kind": definition["kind"],
            "note": definition["note"], "sha256": fingerprint, "files": hashes, "evidence": evidence,
            "graph_url": "artifacts/" + root + "/graph.json", "records_url": "artifacts/" + root + "/records.csv",
            "review_protocol_url": protocol_url,
            "capture_url": "artifacts/" + root + "/sources/capture-manifest.json" if definition["kind"] == "public_snapshot" else None,
            "import_url": "artifacts/" + root + "/import-manifest.json" if definition["kind"] == "public_snapshot" else None}


def bind_dataset(original, dataset, case_id):
    """Bind saved fingerprints, with an explicit exception for two historical cases."""
    recorded = original.get("dataset")
    if recorded is None:
        if case_id not in LEGACY_UNBOUND_CASES or dataset["id"] != "cedar-basin-synthetic-v1":
            raise ValueError("Saved case lacks its required dataset fingerprint")
        return {"recorded_fingerprint_verified": False,
                "note": "This historical run did not save a dataset fingerprint. Its explicit synthetic binding and any ledger source hashes are checked; whole-dataset identity is not established."}
    if (not isinstance(recorded, dict) or any(recorded.get(key) != dataset[key] for key in ("id", "kind", "sha256", "files"))):
        raise ValueError("Saved dataset fingerprint differs from selected showcase dataset")
    return {"recorded_fingerprint_verified": True,
            "note": "Recorded dataset ID, kind, file hashes and aggregate fingerprint match the packaged dataset. Matching bytes do not validate source claims."}


def failure_case(project, definition, dataset, include, files, add):
    """Preserve an explicitly reviewed public execution failure, never invent a report."""
    case_id = definition["id"]
    if (not case_id.startswith("public-") or dataset["kind"] != "public_snapshot"
            or definition["review_state"] != "limited"):
        raise ValueError("Failure cases require a limited public-pilot case binding")
    base = "evaluations/public-pilot/" + case_id + "/"
    if definition.get("review_source") != base + "REVIEW.md":
        raise ValueError("Failure review must use its exact public-pilot artifact root")
    if any(key in definition for key in ("artifact_root", "source_dir", "path", "base")):
        raise ValueError("Configurable failure artifact paths are not allowed")
    for name in ("report.json", "report.md", "evidence-ledger.json"):
        path = project / base / name
        if path.exists() or path.is_symlink():
            raise ValueError("Failure-before-report case contains a report or final ledger")
    artifacts = {name: include(base + name) for name in ("failure.json", "tool-trace.json", "run-metadata.json", "REVIEW.md")}
    artifacts["review"] = artifacts["REVIEW.md"]
    pin = definition.get("metadata_sha256")
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin) or digest(files[artifacts["run-metadata.json"]]) != pin:
        raise ValueError("Original failure metadata differs from its explicit reviewed hash")
    failure, trace, original = [json.loads(files[artifacts[name]]) for name in ("failure.json", "tool-trace.json", "run-metadata.json")]
    if (not isinstance(failure, dict) or set(failure) != {"code", "message"}
            or not isinstance(failure["code"], str) or not re.fullmatch(r"[a-z0-9_]{1,80}", failure["code"])
            or not isinstance(failure["message"], str) or not 1 <= len(failure["message"]) <= 4096):
        raise ValueError("Invalid original failure envelope")
    if (not isinstance(original, dict) or original.get("status") != "failed" or original.get("engine") != "local"
            or original.get("retrieval_profile") != "catalog"
            or not isinstance(original.get("phase"), str) or not re.fullmatch(r"[a-z_]{1,40}", original["phase"])):
        raise ValueError("Failure metadata must record a failed local catalog run")
    binding = bind_dataset(original, dataset, case_id)
    if not isinstance(trace, list) or len(trace) > 100:
        raise ValueError("Invalid bounded failure trace")
    for call in trace:
        if (not isinstance(call, dict) or set(call) != {"name", "args", "status"}
                or not isinstance(call["name"], str) or not isinstance(call["args"], dict)
                or call["status"] not in {"completed", "failed"}):
            raise ValueError("Invalid original failure tool call")
    reads = [call["args"].get("evidence_id") for call in trace if call["name"] == "read_evidence" and call["status"] == "completed"]
    ids = original.get("retrieved_evidence_ids")
    if (not isinstance(ids, list) or len(ids) > 100 or any(not isinstance(eid, str) or eid not in dataset["evidence"] for eid in ids)
            or len(ids) != len(set(ids)) or any(not isinstance(eid, str) for eid in reads) or set(ids) != set(reads)):
        raise ValueError("Recorded retrieved IDs disagree with successful full-read trace or dataset")
    context = None
    admissions = original.get("context_admissions", [])
    if not isinstance(admissions, list) or len(admissions) > 500:
        raise ValueError("Invalid bounded context-admission history")
    if admissions:
        last = admissions[-1]
        if (not isinstance(last, dict) or last.get("policy") != "llama-b11457-text-context-admission-v1"
                or type(last.get("admitted")) is not bool or last.get("exact_model_fit_verified") is not False):
            raise ValueError("Unsupported context-admission policy or result")
        context = {key: last[key] for key in ("policy", "admitted", "exact_model_fit_verified")}
        for key in ("step", "token_limit", "safety_margin", "max_tokens", "prompt_tokens", "reserved_tokens", "remaining_tokens",
                    "generation_request_bytes", "max_request_bytes", "rendered_prompt_bytes"):
            if key in last:
                value = last[key]
                if type(value) is not int or not (-2147483647 if key == "remaining_tokens" else 0) <= value <= 2147483647:
                    raise ValueError("Invalid bounded context-admission metric")
                context[key] = value
        for key in ("canonical_request_sha256", "rendered_prompt_sha256"):
            if key in last:
                if not isinstance(last[key], str) or not re.fullmatch(r"[0-9a-f]{64}", last[key]):
                    raise ValueError("Invalid context-admission fingerprint")
                context[key] = last[key]
    if failure["code"] == "context_token_limit":
        required = ("prompt_tokens", "max_tokens", "safety_margin", "reserved_tokens", "remaining_tokens", "token_limit")
        if (context is None or context["admitted"] or any(key not in context for key in required)
                or context["reserved_tokens"] != sum(context[key] for key in ("prompt_tokens", "max_tokens", "safety_margin"))
                or context["remaining_tokens"] != context["token_limit"] - context["reserved_tokens"]
                or context["reserved_tokens"] <= context["token_limit"]):
            raise ValueError("Context failure lacks consistent recorded overflow measurements")
    metadata = {key: value for key, value in original.items() if key in PUBLIC_METADATA and isinstance(value, (str, int, float, bool))}
    summary = {"phase": original["phase"], "mcp_calls": len(trace),
               "successful_mcp_calls": sum(call["status"] == "completed" for call in trace),
               "full_read_calls": len(reads), "recorded_retrieved_ids": ids, "context_admission": context,
               "retrieval_note": "IDs recorded in run metadata match successful full-read call arguments and the bound dataset. No final citation ledger or analytic report was produced; complete original tool-result bodies are not present in this trace."}
    public_path = "artifacts/" + base + "published-run-summary.json"
    add(public_path, encoded({**metadata, "failure_summary": summary}))
    artifacts["run_summary"] = public_path
    return {**definition, "failure": failure, "trace": trace, "metadata": metadata, "failure_summary": summary,
            "dataset_binding": binding, "review_text": files[artifacts["review"]].decode("utf-8"), "artifacts": artifacts}


def package_files(project=PROJECT):
    files = {}
    def add(path, raw):
        total = sum(map(len, files.values())) - len(files.get(path, b"")) + len(raw)
        if total > MAX_PACKAGE_BYTES:
            raise ValueError("Static package exceeds byte limit")
        files[path] = raw
    config = json.loads(safe_read(project, "showcase/cases.json"))
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported showcase config")
    ids = [case["id"] for case in config["cases"]]
    if len(ids) != len(set(ids)) or config["default_case"] not in ids:
        raise ValueError("Case IDs must be unique and default case must exist")
    for name in ["index.html", "styles.css", "app.js"]:
        add(name, safe_read(project, "showcase/" + name))
    def include(relative):
        path = "artifacts/" + relative
        add(path, safe_read(project, relative))
        return path
    for relative in DOCUMENTS:
        include(relative)
    decisions = files["artifacts/docs/decisions.md"].decode("utf-8")
    prompts = []
    for line in decisions.splitlines():
        if line.startswith("| “"):
            excerpt, consequence = [cell.strip() for cell in line.strip("|").split("|")]
            prompts.append({"excerpt": excerpt, "consequence": consequence})
    if not prompts:
        raise ValueError("No attributed user excerpts found")
    dataset_ids = {case.get("dataset_id") for case in config["cases"]}
    if not all(isinstance(key, str) and key in DATASETS for key in dataset_ids):
        raise ValueError("Every case requires an explicitly allowlisted dataset_id")
    datasets = {key: load_dataset(project, key, include, files) for key in sorted(dataset_ids)}
    cases = []
    for definition in config["cases"]:
        dataset = datasets[definition["dataset_id"]]
        evidence = dataset["evidence"]
        case_id = definition["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", case_id):
            raise ValueError("Invalid case ID")
        if definition["review_state"] not in {"accepted", "limited", "rejected", "pending"}:
            raise ValueError("Invalid review state")
        if definition.get("artifact_kind", "report") == "failure":
            cases.append(failure_case(project, definition, dataset, include, files, add))
            continue
        if definition.get("artifact_kind", "report") != "report":
            raise ValueError("Unsupported case artifact kind")
        base = "examples/" + case_id + "/"
        artifacts = {name: include(base + name) for name in ["report.json", "report.md", "tool-trace.json", "evidence-ledger.json"]}
        report, trace, ledger = [json.loads(files[artifacts[name]]) for name in ["report.json", "tool-trace.json", "evidence-ledger.json"]]
        review_source = definition["review_source"]
        if review_source not in DOCUMENTS and review_source != base + "REVIEW.md":
            raise ValueError("Review source outside explicit case/doc allowlist")
        artifacts["review"] = include(review_source)
        metadata_path = project / base / "run-metadata.json"
        metadata, original = {}, {}
        if metadata_path.is_file() or metadata_path.is_symlink():
            # Never copy full metadata: only the selected non-private scalar fields.
            original = json.loads(safe_read(project, base + "run-metadata.json", scan_text=False))
            if "retrieval_profile" in original and original["retrieval_profile"] not in ("legacy", "catalog"):
                raise ValueError("Unsupported saved retrieval profile")
            metadata = {key: value for key, value in original.items() if key in PUBLIC_METADATA and isinstance(value, (str, int, float, bool))}
            grounding, observation_files = grounded_observation_artifacts(
                original, report, trace, lambda filename: safe_read(project, base + filename))
            if grounding:
                metadata["grounded_media"] = grounding
                for filename, raw in observation_files.items():
                    public_path = "artifacts/" + base + filename
                    add(public_path, raw)
                    artifacts[filename] = public_path
            compact = compact_synthesis_summary(original)
            if compact:
                if not grounding:
                    raise ValueError("Compact synthesis requires verified grounded observations")
                metadata["compact_synthesis"] = compact
            summary_metadata = evidence_summary_metadata(original, report)
            if summary_metadata:
                if not grounding or not compact:
                    raise ValueError("Evidence summary requires verified grounded observations and recorded compact synthesis")
                metadata["evidence_summary"] = summary_metadata
            public_bytes = encoded(metadata)
            if re.search(rb"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", public_bytes) or b"/Users/" in public_bytes or b"/home/" in public_bytes:
                raise ValueError("Machine-specific path in selected run summary")
            public_path = "artifacts/" + base + "published-run-summary.json"
            add(public_path, public_bytes)
            artifacts["run_summary"] = public_path
        binding = bind_dataset(original, dataset, case_id)
        if (dataset["kind"] != "synthetic" and
                "follow_up" in metadata.get("grounded_media", {}).get("constrained_fields", [])):
            raise ValueError("Synthetic fixed follow-up policy cannot label a public dataset")
        verification = []
        for entry in ledger:
            item = evidence.get(entry["id"])
            if item is None:
                raise ValueError("Saved ledger refers to missing source: " + entry["id"])
            verification.append({"id": entry["id"], "text_matches": item["sha256"] == entry["sha256"],
                                 "media_matches": item.get("current_media_sha256") == entry["media_sha256"] if entry.get("media_sha256") else None})
        cited = {eid for group in ["findings", "conflicts"] for finding in report.get(group, []) for eid in finding.get("evidence_ids", [])}
        cited.update(observation["evidence_id"] for observation in report.get("media_observations", []))
        if cited - evidence.keys():
            raise ValueError("Saved report has unavailable source IDs")
        cases.append({**definition, "report": report, "trace": trace, "ledger": ledger, "metadata": metadata,
                      "dataset_binding": binding,
                      "source_verification": verification, "review_text": files[artifacts["review"]].decode("utf-8"),
                      "artifacts": artifacts})
    document_link_gaps = []
    for path, raw in sorted(files.items()):
        if not path.endswith(".md"):
            continue
        for target in re.findall(r"\]\(([^)]+)\)", raw.decode("utf-8")):
            if target.startswith(("https://", "http://", "#")):
                continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target.split("#", 1)[0]))
            if resolved not in files and not any(item.startswith(resolved.rstrip("/") + "/") for item in files):
                document_link_gaps.append({"document": path, "original_target": target, "unavailable_package_target": resolved})
    files["document-link-audit.json"] = encoded({"scope": "Original companion documents may reference repository-only files. These targets are not included in this static package.", "missing_targets": document_link_gaps})
    content = {"schema_version": 2, "project_status": config["project_status"], "default_case": config["default_case"],
               "cases": cases, "datasets": datasets, "prompts": prompts,
               "document_link_gaps": document_link_gaps,
               "replay_note": "Saved outputs and ordered call records. Calls are not re-executed; full historical tool-result payloads were not preserved.",
               "review_note": "Separate-agent source reviews are AI reviews, not independent human labels or held-out accuracy estimates."}
    files["content.json"] = encoded(content)
    if sum(map(len, files.values())) > MAX_PACKAGE_BYTES:
        raise ValueError("Static package exceeds byte limit")
    return files


def build(output, refresh=False, project=PROJECT):
    output = reject_linked_components(output)
    files = package_files(project)
    reject_linked_components(output)
    previous = {}
    if output.exists():
        if not refresh:
            raise ValueError("Output exists; use --refresh only for an unchanged owned package")
        previous = json.loads(safe_read(output, "package-manifest.json"))
        if previous.get("owner") != OWNER:
            raise ValueError("Foreign output directory")
        allowed = {entry["path"]: entry["sha256"] for entry in previous["files"]}
        actual = set()
        pending = [output]
        while pending:
            for path in pending.pop().iterdir():
                reject_linked_components(path)
                if path.is_dir():
                    pending.append(path)
                elif path.is_file():
                    actual.add(path.relative_to(output).as_posix())
                else:
                    raise ValueError("Unsupported output filesystem entry")
        if actual != set(allowed) | {"package-manifest.json"}:
            raise ValueError("Unmanaged output files; use a fresh destination")
        for relative, checksum in allowed.items():
            if digest(safe_read(output, relative)) != checksum:
                raise ValueError("Edited output file; use a fresh destination: " + relative)
        if set(allowed) - set(files):
            raise ValueError("Refresh would remove owned artifacts; use a fresh destination")
    else:
        output.mkdir(parents=True)
        reject_linked_components(output)
    # No deletes, recursive operations or user-file overwrites. Ownership verified above.
    for relative, raw in sorted(files.items()):
        target = reject_linked_components(output / relative)
        if not target.resolve().is_relative_to(output.resolve()):
            raise ValueError("Output path escaped package")
        target.parent.mkdir(parents=True, exist_ok=True)
        reject_linked_components(target)
        target.write_bytes(raw)
    manifest = {"owner": OWNER, "files": [{"path": path, "sha256": digest(raw), "size_bytes": len(raw)} for path, raw in sorted(files.items())]}
    manifest_path = reject_linked_components(output / "package-manifest.json")
    manifest_path.write_bytes(encoded(manifest))
    return {"files": len(files) + 1, "content_bytes": sum(map(len, files.values())), "cases": len(json.loads(files["content.json"])["cases"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=SHOWCASE / "dist")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output_dir, args.refresh), indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("Build refused: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

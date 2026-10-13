"""Bind separate 40-trial replicas without rewriting their freezes or evidence."""
import argparse
import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile

from analytics311.qualification import comparison_qualification
from analytics311.service import AnalyticsService
from analytics311.settings import effective_budgets, validate_manifest
from tools import agent_evaluation as e
from tools.local_agent import metadata_prefix_request


BUDGETS = {"seconds": 160, "request_seconds": 120, "max_calls": 24}
OLD_AGENT = "294a079720ddc9023c715a25bd81b442331647ab7ba167bf2d787966b4845436"
NEW_AGENT = "ca4555771f7c3e99f4b7e1cd932d0a61fbe1e0dad882d0313f6d71b41fd371c7"
OLD_RUNTIME = "2ff41f3779e8c2e342281239f06a22130474f622ab487ffdc2530e5e510a37d9"
NEW_RUNTIME = "0de2a21c278db7d268041173fdb73ab7b928c4f23e5a4dcccc5c44215df15b17"
BASELINE_FREEZE = "080e76a2e1635bba36ace74a398097f3d7be2789fa8fdb609929c0970c228490"
BASELINE_WARMUP_HASHES = {
    "447336be8215511ea42951aeb089c64cc358ce683d865bf54ba36480f8cd3f97",
    "7ae033d90bd32bdf93956f997ae513409027b2234ae022ffa714d11f7bd7dd9f",
    "b0d924f9917e7db765d5eaff5fc040a7682d260b926d6a50c7d8f9a239494d67",
}
MANIFEST_REPLICA_PATHS = (
    ("extracted_at",), ("index_uuid",), ("ingestion", "index_uuid"),
    ("comparison_qualification", "index_uuid"),
    ("comparison_qualification", "qualification_sha256"),
)
PROFILE_PATHS = ("manifest_path", "catalog_path", "runs_dir")
KIBANA_IDS = ("boundary_view_id", "data_view_id", "map_id", "trend_data_view_id", "trend_map_id")
FREEZE_REPLICA_KEYS = ("created_at", "manifest_sha256", "prefix_warmup_request")


def require(condition, code):
    if not condition:
        raise ValueError(code)


def same(left, right):
    """Canonical JSON distinguishes booleans, integers and floating-point values."""
    return e.digest(left) == e.digest(right)


def logical_manifest(manifest):
    validate_manifest(manifest)
    require(comparison_qualification(manifest) is not None, "unqualified_replica")
    result = copy.deepcopy(manifest)
    for path in MANIFEST_REPLICA_PATHS:
        node = result
        for key in path[:-1]:
            node = node[key]
        require(isinstance(node.get(path[-1]), str) and bool(node[path[-1]]), "missing_replica_manifest_field")
        del node[path[-1]]
    return result


def logical_profile(profile, provision):
    result = copy.deepcopy(profile)
    for key in PROFILE_PATHS:
        require(isinstance(result.get(key), str) and bool(result[key]), "missing_replica_profile_path")
        del result[key]
    require(result.get("backend") == "elastic", "real_elastic_replica_required")
    require(provision.get("passed") is True and provision.get("schema_version") == 1
            and provision.get("source_index") == result.get("index")
            and provision.get("checks", {}).get("exact_no_time_data_views") is True
            and provision.get("checks", {}).get("boundary_count") == 262,
            "map_provisioning_required")
    ids = provision.get("map_ids", {})
    kibana = result.get("kibana", {})
    require(set(ids) == set(KIBANA_IDS)
            and all(isinstance(ids[key], str) and bool(ids[key]) and kibana.get(key) == ids[key] for key in KIBANA_IDS)
            and all(kibana.get(key) == provision.get(key) and isinstance(kibana.get(key), str)
                    for key in ("result_index", "boundary_index")), "map_profile_binding_changed")
    for key in KIBANA_IDS:
        del result["kibana"][key]
    # Everything else, including unknown configuration and all analytical limits, stays bound.
    return result


def logical_provision(provision):
    result = copy.deepcopy(provision)
    require(isinstance(result.get("started_at"), str) and bool(result["started_at"]), "map_provision_start_missing")
    del result["started_at"]
    del result["map_ids"]
    return result


def logical_freeze(frozen):
    result = copy.deepcopy(frozen)
    for key in FREEZE_REPLICA_KEYS:
        require(key in result, "missing_replica_freeze_field")
        del result[key]
    return result


def logical_execution(identity):
    result = copy.deepcopy(identity)
    del result["freeze_sha256"]
    files = result["runtime"]["files"]
    # Native builds and dynamic libraries may differ between runner CPUs. The
    # downloaded model and source revision must remain byte-identical.
    require(isinstance(files, list) and len(files) >= 3, "execution_file_inventory_missing")
    require(all(isinstance(item, dict) and item.get("role") in
                {"model", "source_revision", "server", "build_configuration", "runtime_library"}
                for item in files), "unexpected_execution_file_role")
    result["runtime"]["files"] = [item for item in files if item.get("role") in {"model", "source_revision"}]
    require(sum(item.get("role") == "model" for item in files) == 1
            and sum(item.get("role") == "source_revision" for item in files) == 1, "execution_model_or_source_missing")
    return result


def metadata_identity(manifest, catalog, profile, alias):
    # describe_dataset is metadata-only. Bypass construction so archived absolute
    # file paths cannot cause reads, writes or a query to a different service.
    service = AnalyticsService.__new__(AnalyticsService)
    service.manifest, service.catalog, service.config = manifest, catalog, profile
    service.budgets = effective_budgets(profile.get("budgets", {}))
    return metadata_prefix_request(service.describe_dataset(), alias)[1]


def replica_metadata(root):
    root = Path(root)
    acceptance_path = root / "real-v1/acceptance.json"
    acceptance = e.load(acceptance_path)
    require(acceptance.get("agent_config") == "maps-profile.json", "configured_maps_agent_required")
    paths = {"freeze": root / "real-v1/agent-freeze.json",
             "manifest": root / "real-v1/index.manifest.json",
             "catalog": root / "real-v1/catalog.json", "profile": root / "real-v1/maps-profile.json",
             "provision": root / "real-v1/maps-provision.json", "acceptance": acceptance_path}
    data = {key: e.load(path) for key, path in paths.items()}
    frozen = data["freeze"]
    require(frozen["manifest_sha256"] == e.digest(data["manifest"]), "replica_manifest_hash_changed")
    require(frozen["catalog_sha256"] == e.digest(data["catalog"]), "replica_catalog_hash_changed")
    require(same(frozen["prefix_warmup_request"], metadata_identity(data["manifest"], data["catalog"],
                    data["profile"], frozen["model"])), "replica_metadata_prefix_changed")
    logical_manifest(data["manifest"])
    logical_profile(data["profile"], data["provision"])
    require(data["provision"].get("boundaries_sha256") == frozen["nta_sha256"]
            and data["provision"].get("dataset_version") == data["manifest"].get("dataset_version"),
            "map_provision_dataset_changed")
    return paths, data


def prepare(baseline_root, output):
    """Prospectively pin the three-replica study from its zero-exposure predecessor."""
    paths, data = replica_metadata(baseline_root)
    frozen = data["freeze"]
    require(e.sha_file(paths["freeze"]) == BASELINE_FREEZE, "different_predecessor_freeze")
    runs = Path(baseline_root) / "agent-v1"
    summary = e.load(runs / "summary.json")
    require(not list(runs.glob("Q*-r*.json")) and summary.get("attempted_trials") == 0
            and summary.get("execution_complete") is False, "baseline_exposed_to_questions")
    warm_paths = sorted(runs.glob("metadata-prefix-warmup-*.json"))
    require(len(warm_paths) == 3, "three_original_startup_failures_required")
    require({e.sha_file(path) for path in warm_paths} == BASELINE_WARMUP_HASHES, "different_original_startup_failures")
    for path in warm_paths:
        warm = e.load(path)
        require(warm.get("passed") is False and warm.get("error") == {"code": "model_timeout"}
                and warm.get("question_supplied") is False and warm.get("analytical_tool_calls") == 0
                and warm.get("request_seconds") == 300
                and same({key: warm.get(key) for key in frozen["prefix_warmup_request"]},
                         frozen["prefix_warmup_request"]), "baseline_startup_evidence_changed")
    old_code, new_code = frozen["code_sha256"], e.code_hashes()
    require(old_code.get("tools/local_agent.py") == OLD_AGENT and new_code.get("tools/local_agent.py") == NEW_AGENT
            and same({**old_code, "tools/local_agent.py": NEW_AGENT}, new_code), "non_startup_candidate_change")
    runtime = e.runtime_definition(e.RUNTIME_SPEC, frozen["model"])
    old_definition = copy.deepcopy(runtime["definition"])
    old_definition["inference"]["prefix_warmup"]["request_seconds"] = 300
    require(frozen["runtime_spec"]["sha256"] == OLD_RUNTIME and runtime["sha256"] == NEW_RUNTIME
            and same(old_definition, frozen["runtime_spec"]["definition"]), "non_startup_runtime_change")
    require(len(frozen["cases"]) == 40 and frozen["required_trials"] == 120 and frozen["repetitions"] == 3
            and frozen["pass_threshold"] == .9 and frozen["minimum_passes_per_question"] == 1
            and frozen["semantic_review_required"] is True and frozen["development_only"] is False,
            "baseline_protocol_changed")
    expected = logical_freeze(frozen)
    expected.update(code_sha256=new_code, runtime_spec=runtime)
    execution = logical_execution(e.load(runs / "run-identity.json"))
    require(same({key: execution.get(key) for key in BUDGETS}, BUDGETS)
            and same(execution["runtime"].get("budgets"), BUDGETS), "baseline_budgets_changed")
    execution["runtime"]["runtime_spec_sha256"] = runtime["sha256"]
    protocol = {"schema_version": 1, "evidence_kind": "prospective_three_replica_agent_campaign",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "merger_sha256": e.sha_file(__file__), "baseline_freeze_sha256": e.sha_file(paths["freeze"]),
                "baseline_warmup_receipts": {path.name: e.sha_file(path) for path in warm_paths},
                "candidate_amendment": {"old_agent_sha256": OLD_AGENT, "new_agent_sha256": NEW_AGENT,
                                        "old_runtime_sha256": OLD_RUNTIME, "new_runtime_sha256": NEW_RUNTIME,
                                        "change": "One metadata-only startup request bound increased300 to900 seconds; no analytical request change."},
                "trial_budgets": BUDGETS, "freeze_invariants": expected,
                "execution_invariants": execution,
                "logical_manifest": logical_manifest(data["manifest"]),
                "logical_profile": logical_profile(data["profile"], data["provision"]),
                "logical_map_provision": logical_provision(data["provision"]),
                "manifest_replica_paths": [list(path) for path in MANIFEST_REPLICA_PATHS],
                "profile_path_fields": list(PROFILE_PATHS), "freeze_replica_keys": list(FREEZE_REPLICA_KEYS),
                "kibana_replica_id_fields": list(KIBANA_IDS),
                "limits": ["Three host-local replicas may have different native binaries, linked libraries, CPU features and latency.",
                           "Each replica retains its own frozen index UUID, qualification certificate, metadata request and execution identity.",
                           "This is one120-trial campaign; missing or failed trials remain in the denominator. No human-gold claim."]}
    e.write_new(output, protocol)
    return protocol


def load_protocol(path):
    protocol = e.load(path)
    require(protocol.get("schema_version") == 1
            and protocol.get("evidence_kind") == "prospective_three_replica_agent_campaign"
            and protocol.get("merger_sha256") == e.sha_file(__file__)
            and same(protocol.get("trial_budgets"), BUDGETS)
            and same(protocol.get("manifest_replica_paths"), [list(value) for value in MANIFEST_REPLICA_PATHS])
            and same(protocol.get("profile_path_fields"), list(PROFILE_PATHS))
            and same(protocol.get("kibana_replica_id_fields"), list(KIBANA_IDS))
            and same(protocol.get("freeze_replica_keys"), list(FREEZE_REPLICA_KEYS)), "campaign_protocol_changed")
    require(same(protocol["freeze_invariants"]["code_sha256"], e.code_hashes())
            and protocol["freeze_invariants"]["runtime_spec"]["sha256"] == e.sha_file(e.RUNTIME_SPEC),
            "campaign_candidate_source_changed")
    return protocol


def verify_replica(protocol, root, repetition):
    require(type(repetition) is int and repetition in (1, 2, 3), "invalid_replica_number")
    paths, data = replica_metadata(root)
    require(same(logical_freeze(data["freeze"]), protocol["freeze_invariants"]), "replica_freeze_invariants_changed")
    require(same(logical_manifest(data["manifest"]), protocol["logical_manifest"]), "replica_logical_manifest_changed")
    require(same(logical_profile(data["profile"], data["provision"]), protocol["logical_profile"]), "replica_profile_changed")
    require(same(logical_provision(data["provision"]), protocol["logical_map_provision"]), "replica_map_provision_changed")
    return {"repetition": repetition, "freeze_sha256": e.sha_file(paths["freeze"]),
            "index_uuid": data["manifest"]["index_uuid"], "metadata_prefix_request": data["freeze"]["prefix_warmup_request"],
            "metadata_files": {key: e.sha_file(path) for key, path in paths.items()}}


def merge(protocol_path, replicas, output, reviews=None):
    protocol = load_protocol(protocol_path)
    reviews = reviews or {}
    require(set(reviews) <= set(replicas), "review_without_replica")
    trials, reports, semantic_reports = [], [], []
    frozen = protocol["freeze_invariants"]
    case_by_id = {case["id"]: case for case in frozen["cases"]}
    with tempfile.TemporaryDirectory(prefix="analytics311-campaign-review-") as temporary:
        temporary = Path(temporary)
        for repeat, root in sorted(replicas.items()):
            proof = verify_replica(protocol, root, repeat)
            root = Path(root)
            runs, freeze_path = root / "agent-v1", root / "real-v1/agent-freeze.json"
            identity = e.load(runs / "run-identity.json")
            runtime = identity.get("runtime", {})
            require(identity.get("freeze_sha256") == proof["freeze_sha256"] and identity.get("model") == frozen["model"]
                    and same({key: identity.get(key) for key in BUDGETS}, BUDGETS)
                    and same(runtime.get("budgets"), BUDGETS)
                    and runtime.get("model_alias") == frozen["model"], "replica_execution_budgets_changed")
            require(same(logical_execution(identity), protocol["execution_invariants"]), "replica_execution_policy_changed")
            paths = sorted(runs.glob("Q*-r*.json"))
            current = []
            for path in paths:
                trial = e.load(path)
                qid, trace = trial.get("question_id"), trial.get("trace", {})
                require(qid in case_by_id and type(trial.get("repeat")) is int and trial["repeat"] == repeat
                        and path.name == f"{qid}-r{repeat}.json" and trace.get("question") == case_by_id[qid]["question"]
                        and trace.get("model") == frozen["model"] and type(trace.get("seed")) is int
                        and trace["seed"] == frozen["model_settings"]["seeds"][repeat-1], "foreign_replica_trial")
                current.append(trial)
            review_path = reviews.get(repeat)
            if review_path is None:
                # No semantic scores are invented. Reuse the existing offline
                # binding validator with zero judgments; its incomplete report is explicit.
                review_path = temporary / f"empty-reviews-{repeat}.json"
                e.write_new(review_path, {"freeze_sha256": proof["freeze_sha256"],
                    "reviewer": {"id": "archive-binding-only-no-judgments", "kind": "independent_ai_session",
                                 "was_answering_agent": False}, "reviews": []})
            subreport = e.review(freeze_path, [runs], review_path, temporary / f"review-{repeat}.json")
            semantic_reports.append(subreport)
            proof.update(execution_sha256=e.digest(identity), runtime_identity=runtime,
                         trial_files={path.name: e.sha_file(path) for path in paths}, attempted_trials=len(current),
                         reviewed_trials=subreport["reviewed_trials"],
                         model_latency_seconds=subreport["model_latency_seconds"],
                         semantic_reviews_sha256=e.sha_file(review_path) if repeat in reviews else None,
                         prefix_warmup=subreport["prefix_warmup"],
                         host_sha256=e.sha_file(root / "runtime/host.json") if (root / "runtime/host.json").exists() else None,
                         cpu_sha256=e.sha_file(root / "runtime/cpu.txt") if (root / "runtime/cpu.txt").exists() else None)
            trials.extend(current)
            reports.append(proof)
    report = e.summarize(frozen, trials)
    reviewed = sum(item["reviewed_trials"] for item in semantic_reports)
    passed = sum(item["end_to_end_passes"] for item in semantic_reports)
    per_question = {qid: sum(item["end_to_end_by_question"][qid] for item in semantic_reports) for qid in case_by_id}
    fabrication = [key for item in semantic_reports for key in item["semantic_fabrication_or_false_completion"]]
    report.update(schema_version=1, evidence_kind="three_replica_agent_campaign_result",
                  protocol_sha256=e.sha_file(protocol_path), replicas=reports,
                  execution_complete=len(trials) == 120 and not report["missing_trials"] and not report["invalid_or_duplicate_trials"],
                  semantic_review="complete" if reviewed == 120 else "incomplete", reviewed_trials=reviewed,
                  end_to_end_passes=passed, end_to_end_pass_rate=passed / 120, end_to_end_by_question=per_question,
                  semantic_fabrication_or_false_completion=fabrication,
                  agent_quality_gate_passed=reviewed == 120 and report["automatic_gate_passed"]
                    and passed / 120 >= frozen["pass_threshold"] and all(value >= 1 for value in per_question.values()) and not fabrication,
                  startup_seconds_total=sum(item["prefix_warmup"]["startup_seconds_total"] for item in reports),
                  release_verified=False, visual_parity_verified=False, second_agent_client_verified=False)
    report["limitations"] += protocol["limits"] + ["Offline archive checks do not cryptographically attest the original runner; artifact provenance is retained separately."]
    e.write_new(output, report)
    return report


def assignments(values):
    result = {}
    for value in values:
        number, path = value.split("=", 1)
        require(number in {"1", "2", "3"} and bool(path) and int(number) not in result, "duplicate_or_invalid_replica")
        result[int(number)] = Path(path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("prepare")
    create.add_argument("--baseline-root", required=True)
    create.add_argument("--output", required=True)
    verify = commands.add_parser("verify-replica")
    verify.add_argument("--protocol", required=True)
    verify.add_argument("--root", required=True)
    verify.add_argument("--repetition", type=int, required=True)
    combine = commands.add_parser("merge")
    combine.add_argument("--protocol", required=True)
    combine.add_argument("--replica", action="append", default=[])
    combine.add_argument("--reviews", action="append", default=[])
    combine.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.baseline_root, args.output)
    elif args.command == "verify-replica":
        verify_replica(load_protocol(args.protocol), args.root, args.repetition)
    else:
        report = merge(args.protocol, assignments(args.replica), args.output, assignments(args.reviews))
        return 0 if report["automatic_gate_passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

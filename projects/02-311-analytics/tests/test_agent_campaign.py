"""Authored offline archive fixtures; these are never model evaluation evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from analytics311.qualification import qualify_frozen_index
from tests.test_qualification import frozen as qualification_fixture
from tools import agent_campaign as c, agent_evaluation as e


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def fixture(root, repetition, *, native_hash="s" * 64):
    normalized, ingestion, snapshot, bounds, manifest = qualification_fixture()
    manifest.update(dataset_version="authored-campaign-unit", extracted_at=f"2026-01-0{repetition}T00:00:00Z")
    manifest["index_uuid"] = manifest["ingestion"]["index_uuid"] = f"replica-{repetition}"
    manifest["comparison_qualification"] = qualify_frozen_index(normalized, ingestion, manifest, bounds)
    profile = {"backend": "elastic", "index": manifest["index"], "budgets": {"max_preview_rows": 100},
               "manifest_path": f"/replica-{repetition}/manifest.json", "catalog_path": "/replica/catalog.json",
               "runs_dir": "/replica/results", "kibana": {key: f"{key}-{repetition}" for key in c.KIBANA_IDS}}
    profile["kibana"].update(result_index="unit-results", boundary_index="unit-boundaries")
    provision = {"schema_version": 1, "passed": True, "source_index": manifest["index"],
                 "dataset_version": manifest["dataset_version"], "boundaries_sha256": "n" * 64,
                 "result_index": "unit-results", "boundary_index": "unit-boundaries",
                 "started_at": f"2026-01-0{repetition}T00:00:00Z",
                 "map_ids": {key: profile["kibana"][key] for key in c.KIBANA_IDS},
                 "checks": {"exact_no_time_data_views": True, "boundary_count": 262}}
    catalog = {"families": {"noise": ["Noise"]}, "version": "unit"}
    definition = e.load(e.RUNTIME_SPEC)
    cases = [{"id": f"Q{i:02}", "question": f"Authored unit question {i}", "steps": []} for i in range(1, 41)]
    frozen = {"created_at": f"2026-01-0{repetition}T00:00:00Z", "cases": cases,
              "model": definition["model_alias"], "model_settings": {"temperature": .2, "seeds": [101, 202, 303], "max_tokens": 2048},
              "runtime_spec": {"sha256": c.NEW_RUNTIME, "definition": definition},
              "code_sha256": e.code_hashes(), "questions_sha256": "q" * 64,
              "database_sha256": "d" * 64, "source": {"rows": 2, "source_sha256": "c" * 64, "source_bytes": 300},
              "nta_sha256": "n" * 64, "catalog_sha256": e.digest(catalog), "manifest_sha256": e.digest(manifest),
              "pass_threshold": .9, "minimum_passes_per_question": 1, "required_trials": 120,
              "development_only": False, "semantic_review_required": True, "repetitions": 3,
              "prefix_warmup_request": c.metadata_identity(manifest, catalog, profile, definition["model_alias"])}
    real = root / "real-v1"
    for name, value in (("agent-freeze", frozen), ("index.manifest", manifest), ("catalog", catalog),
                        ("maps-profile", profile), ("maps-provision", provision),
                        ("acceptance", {"agent_config": "maps-profile.json"})):
        save(real / (name + ".json"), value)
    freeze_hash = e.sha_file(real / "agent-freeze.json")
    runtime = {"runtime_spec_sha256": c.NEW_RUNTIME, "execution_runtime": definition["execution_runtime"],
               "model_alias": frozen["model"], "endpoint": ["127.0.0.1", 8080, "/v1"], "budgets": c.BUDGETS,
               "launch_arguments": ["<server>", "--threads", "4", "--ctx-size", "24576"],
               "files": [{"role": "model", "bytes": 10, "sha256": "a" * 64},
                         {"role": "source_revision", "bytes": 41, "sha256": "b" * 64},
                         {"role": "server", "bytes": 20, "sha256": native_hash}]}
    identity = {"freeze_sha256": freeze_hash, "model": frozen["model"], **c.BUDGETS, "runtime": runtime}
    runs = root / "agent-v1"
    save(runs / "run-identity.json", identity)
    execution_hash = e.digest(identity)
    receipt = {"unit_only": True, "pid": repetition, "model": frozen["model"]}
    receipt_json = json.dumps(receipt)
    import hashlib
    launch_hash = hashlib.sha256(receipt_json.encode()).hexdigest()
    save(runs / f"runtime-launch-{launch_hash}.json",
         {"sha256": launch_hash, "receipt_json": receipt_json, "receipt": receipt, "identity": runtime})
    warm = {"schema_version": 1, "evidence_kind": "metadata_only_model_prefix_warmup", "passed": True,
            "runtime_receipt_sha256": launch_hash, "runtime_spec_sha256": c.NEW_RUNTIME,
            "execution_sha256": execution_hash, "model_alias": frozen["model"],
            "question_supplied": False, "analytical_tool_calls": 0, "generated_content_retained": False,
            "usage": {"prompt_tokens": 123, "completion_tokens": 1, "total_tokens": 124}, "elapsed_seconds": 310,
            **definition["inference"]["prefix_warmup"], **frozen["prefix_warmup_request"]}
    warm_path = runs / f"metadata-prefix-warmup-{launch_hash}.json"
    save(warm_path, warm)
    judgments = []
    for case in cases:
        trial = {"question_id": case["id"], "repeat": repetition, "freeze_sha256": freeze_hash,
                 "execution_sha256": execution_hash, "runtime_receipt_sha256": launch_hash,
                 "prefix_warmup_sha256": e.sha_file(warm_path),
                 "trace": {"question": case["question"], "model": frozen["model"], "seed": 101 * repetition,
                           "elapsed_seconds": 1, "unit_fixture_only": True},
                 "grade": {"automatic_pass": True, "hard_failures": []}}
        path = runs / f"{case['id']}-r{repetition}.json"
        save(path, trial)
        judgments.append({"question_id": case["id"], "repeat": repetition, "trial_sha256": e.sha_file(path),
                          "checks": {key: True for key in e.REVIEW_CHECKS}, "notes": "Authored fixture only."})
    save(root / "reviews.json", {"freeze_sha256": freeze_hash,
         "reviewer": {"id": "unit-only", "kind": "independent_ai_session", "was_answering_agent": False}, "reviews": judgments})
    return frozen, manifest, profile, identity, provision


def protocol(root, values):
    frozen, manifest, profile, identity, provision = values
    result = {"schema_version": 1, "evidence_kind": "prospective_three_replica_agent_campaign",
              "merger_sha256": e.sha_file(c.__file__), "trial_budgets": c.BUDGETS,
              "freeze_invariants": c.logical_freeze(frozen), "logical_manifest": c.logical_manifest(manifest),
              "logical_profile": c.logical_profile(profile, provision), "execution_invariants": c.logical_execution(identity),
              "logical_map_provision": c.logical_provision(provision), "kibana_replica_id_fields": list(c.KIBANA_IDS),
              "manifest_replica_paths": [list(x) for x in c.MANIFEST_REPLICA_PATHS],
              "profile_path_fields": list(c.PROFILE_PATHS), "freeze_replica_keys": list(c.FREEZE_REPLICA_KEYS),
              "limits": ["Authored unit fixtures; no actual inference."]}
    path = root / "protocol.json"
    save(path, result)
    return path


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.replicas = {i: self.root / f"replica-{i}" for i in (1, 2, 3)}
        self.values = {i: fixture(path, i, native_hash=str(i) * 64) for i, path in self.replicas.items()}
        self.protocol = protocol(self.root, self.values[1])

    def merge(self, replicas=None, reviews=None):
        return c.merge(self.protocol, self.replicas if replicas is None else replicas,
                       self.root / "result.json", reviews)

    def test_three_native_replicas_keep_own_bindings_and_full_semantic_gate(self):
        report = self.merge(reviews={i: path / "reviews.json" for i, path in self.replicas.items()})
        self.assertEqual((report["attempted_trials"], report["reviewed_trials"], report["end_to_end_passes"]), (120, 120, 120))
        self.assertTrue(report["agent_quality_gate_passed"])
        self.assertFalse(report["release_verified"])
        self.assertEqual(len({r["freeze_sha256"] for r in report["replicas"]}), 3)
        self.assertEqual(len({r["execution_sha256"] for r in report["replicas"]}), 3)
        self.assertEqual(report["startup_seconds_total"], 930)

    def test_automatic_success_cannot_invent_semantic_review(self):
        report = self.merge()
        self.assertTrue(report["automatic_gate_passed"])
        self.assertEqual(report["reviewed_trials"], 0)
        self.assertFalse(report["agent_quality_gate_passed"])

    def test_missing_replica_stays_in_fixed_denominator(self):
        report = self.merge({1: self.replicas[1], 3: self.replicas[3]})
        self.assertEqual((report["required_trials"], report["attempted_trials"], len(report["missing_trials"])), (120, 80, 40))
        self.assertEqual(report["automatic_pass_rate"], 80 / 120)
        self.assertFalse(report["execution_complete"])

    def test_failed_trial_preserved_without_replacement(self):
        path = self.replicas[1] / "agent-v1/Q01-r1.json"
        trial = e.load(path); trial["grade"]["automatic_pass"] = False; save(path, trial)
        before = path.read_bytes()
        report = self.merge()
        self.assertEqual(report["automatic_passes"], 119)
        self.assertEqual(path.read_bytes(), before)

    def test_cross_replica_seed_question_and_filename_rejected(self):
        path = self.replicas[2] / "agent-v1/Q01-r2.json"; original = e.load(path)
        for field, value in (("seed", 101), ("question", "foreign"), ("model", "foreign")):
            trial = copy.deepcopy(original); trial["trace"][field] = value; save(path, trial)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "foreign_replica_trial"):
                self.merge()
        save(path, {**original, "repeat": 1})
        with self.assertRaisesRegex(ValueError, "foreign_replica_trial"):
            self.merge()

    def test_changed_frozen_database_or_oracle_rejected(self):
        path = self.replicas[2] / "real-v1/agent-freeze.json"; original = e.load(path)
        for field in ("database_sha256", "questions_sha256", "nta_sha256"):
            changed = copy.deepcopy(original); changed[field] = "x" * 64; save(path, changed)
            expected_error = "map_provision_dataset_changed" if field == "nta_sha256" else "freeze_invariants"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, expected_error):
                self.merge()
        changed = copy.deepcopy(original); changed["cases"][0]["steps"] = [{"invented": "oracle"}]; save(path, changed)
        with self.assertRaisesRegex(ValueError, "freeze_invariants"):
            self.merge()

    def test_qualification_revalidated_before_volatile_fields_ignored(self):
        manifest = copy.deepcopy(self.values[1][1])
        manifest["index_uuid"] = "unbound"
        with self.assertRaises(Exception):
            c.logical_manifest(manifest)
        manifest = copy.deepcopy(self.values[1][1]); manifest["comparison_qualification"]["qualification_sha256"] = "0" * 64
        with self.assertRaises(Exception):
            c.logical_manifest(manifest)

    def test_unknown_metadata_and_analytical_limits_remain_bound(self):
        root = self.replicas[2]; profile_path = root / "real-v1/maps-profile.json"
        profile = e.load(profile_path); profile["budgets"]["max_preview_rows"] = 50; save(profile_path, profile)
        with self.assertRaisesRegex(ValueError, "metadata_prefix"):
            self.merge()
        self.assertFalse(c.same({"count": 1}, {"count": True}))
        original = self.values[1][1]; changed = {**original, "unknown_source_note": "Retain me"}
        self.assertFalse(c.same(c.logical_manifest(original), c.logical_manifest(changed)))

    def test_launch_policy_and_budgets_cannot_vary_with_native_host(self):
        path = self.replicas[2] / "agent-v1/run-identity.json"; identity = e.load(path)
        identity["runtime"]["launch_arguments"] += ["--threads", "8"]; save(path, identity)
        with self.assertRaisesRegex(ValueError, "execution_policy"):
            self.merge()

    def test_relabelled_warmup_and_changed_semantic_trial_hash_rejected(self):
        root = self.replicas[1]; trial_path = root / "agent-v1/Q01-r1.json"; trial = e.load(trial_path)
        trial["prefix_warmup_sha256"] = "0" * 64; save(trial_path, trial)
        with self.assertRaisesRegex(ValueError, "prefix_warmup_receipt_changed"):
            self.merge()

    def test_semantic_reviews_cannot_follow_modified_trial_bytes(self):
        path = self.replicas[1] / "agent-v1/Q01-r1.json"
        trial = e.load(path); trial["trace"]["elapsed_seconds"] = 2; save(path, trial)
        with self.assertRaisesRegex(ValueError, "review_does_not_match_exact_trial"):
            self.merge(reviews={1: self.replicas[1] / "reviews.json"})

    def test_unknown_native_file_roles_are_not_a_portability_exemption(self):
        identity = copy.deepcopy(self.values[1][3])
        identity["runtime"]["files"].append({"role": "unknown_policy", "sha256": "f" * 64, "bytes": 1})
        with self.assertRaisesRegex(ValueError, "unexpected_execution_file_role"):
            c.logical_execution(identity)

    def test_changing_trial_budgets_is_rejected_before_review(self):
        path = self.replicas[2] / "agent-v1/run-identity.json"
        identity = e.load(path); identity["request_seconds"] = 900; save(path, identity)
        with self.assertRaisesRegex(ValueError, "execution_budgets"):
            self.merge()

    def test_duplicate_replica_assignments_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate_or_invalid_replica"):
            c.assignments(["1=a", "1=b"])
        with self.assertRaisesRegex(ValueError, "duplicate_or_invalid_replica"):
            c.assignments(["4=a"])

    def test_placeholder_profile_and_unbound_kibana_ids_cannot_pass(self):
        root = self.replicas[2]
        acceptance = root / "real-v1/acceptance.json"
        save(acceptance, {"agent_config": "profile.json"})
        with self.assertRaisesRegex(ValueError, "configured_maps_agent_required"):
            self.merge()
        save(acceptance, {"agent_config": "maps-profile.json"})
        path = root / "real-v1/maps-profile.json"; profile = e.load(path)
        profile["kibana"]["map_id"] = "foreign-map"; save(path, profile)
        with self.assertRaisesRegex(ValueError, "map_profile_binding_changed"):
            self.merge()


if __name__ == "__main__":
    unittest.main()

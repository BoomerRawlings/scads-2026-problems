"""Artifact/content/package checks; browser interaction verification is separate."""
import hashlib
import base64
import csv
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts import build_showcase as builder


class ShowcaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = builder.package_files()
        cls.content = json.loads(cls.files["content.json"])

    def test_original_artifacts_and_recorded_outcomes(self):
        config = json.loads((PROJECT / "showcase/cases.json").read_bytes())
        self.assertEqual([case["id"] for case in self.content["cases"]], [case["id"] for case in config["cases"]])
        self.assertEqual(self.content["default_case"], config["default_case"])
        self.assertEqual(self.content["project_status"], config["project_status"])
        for case in self.content["cases"]:
            if case.get("artifact_kind") == "failure":
                self.assertNotIn("report", case)
                self.assertNotIn("ledger", case)
                for name in ("failure.json", "run-metadata.json", "tool-trace.json", "REVIEW.md"):
                    self.assertEqual(self.files[case["artifacts"][name]], (PROJECT / "evaluations/public-pilot" / case["id"] / name).read_bytes())
                continue
            for name in ["report.json", "report.md", "tool-trace.json", "evidence-ledger.json"]:
                self.assertEqual(self.files[case["artifacts"][name]], (PROJECT / "examples" / case["id"] / name).read_bytes())
            if case["id"].endswith("rejected"):
                self.assertEqual(case["review_state"], "rejected")
                self.assertEqual(case["report"]["status"], "complete")
            self.assertTrue(all(item["text_matches"] and item["media_matches"] is not False for item in case["source_verification"]))
            for record in case["metadata"].get("grounded_media", {}).get("observations", []):
                raw = self.files[case["artifacts"][record["path"]]]
                self.assertEqual(raw, (PROJECT / "examples" / case["id"] / record["path"]).read_bytes())
                self.assertEqual(builder.digest(raw), record["output_sha256"])
        self.assertEqual(len(next(case for case in self.content["cases"] if case["id"] == "cbri")["trace"]), 24)

    def test_report_markdown_sources_resolve_within_package(self):
        for case in self.content["cases"]:
            if case.get("artifact_kind") == "failure":
                continue
            path = case["artifacts"]["report.md"]
            markdown = self.files[path].decode("utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", markdown):
                if target.startswith(("https://", "http://")):
                    continue
                target = target.split("#", 1)[0]
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                self.assertIn(resolved, self.files, (case["id"], target))
        for dataset in self.content["datasets"].values():
            for source in dataset["evidence"].values():
                self.assertIn(source["file_url"], self.files)
                if source.get("media_url"):
                    self.assertIn(source["media_url"], self.files)

    def test_private_runtime_state_excluded_and_excerpts_attributed(self):
        paths = list(self.files)
        reviewed_metadata = {case["artifacts"]["run-metadata.json"] for case in self.content["cases"] if case.get("artifact_kind") == "failure"}
        self.assertFalse(any(("run-metadata.json" in path and path not in reviewed_metadata) or "/runs/" in path or ".venv" in path or ".codex" in path for path in paths))
        self.assertTrue(all(path in {"index.html", "styles.css", "app.js", "content.json", "document-link-audit.json"} or path.startswith("artifacts/") for path in paths))
        self.assertEqual(len(self.content["prompts"]), 5)
        decision_text = (PROJECT / "docs/decisions.md").read_text(encoding="utf-8")
        for prompt in self.content["prompts"]:
            self.assertIn(prompt["excerpt"], decision_text)
        for case in self.content["cases"]:
            self.assertLessEqual(case["metadata"].keys(), builder.PUBLIC_METADATA | {"grounded_media", "compact_synthesis", "evidence_summary"})
        # No source or report text is inserted as executable HTML.
        js = self.files["app.js"].decode("utf-8")
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("eval(", js)

    def test_owned_refresh_is_deterministic_and_preserves_edited_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "viewer"
            builder.build(output)
            before = (output / "package-manifest.json").read_bytes()
            builder.build(output, refresh=True)
            self.assertEqual(before, (output / "package-manifest.json").read_bytes())
            for entry in json.loads(before)["files"]:
                self.assertEqual(hashlib.sha256((output / entry["path"]).read_bytes()).hexdigest(), entry["sha256"])
            (output / "index.html").write_text("user edit", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Edited output"):
                builder.build(output, refresh=True)
            self.assertEqual((output / "index.html").read_text(), "user edit")

    def test_foreign_files_and_escape_sources_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "viewer"
            builder.build(output)
            foreign = output / "keep.txt"
            foreign.write_text("keep me", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unmanaged output"):
                builder.build(output, refresh=True)
            self.assertEqual(foreign.read_text(), "keep me")
            with self.assertRaisesRegex(ValueError, "contained relative"):
                builder.safe_read(PROJECT, "../other-project/file.txt")

    def test_metadata_read_is_bounded_and_unavailable_document_links_identified(self):
        from unittest.mock import patch
        original = builder.safe_read
        bounded_metadata = []
        pinned_failure_metadata = {case["artifacts"]["run-metadata.json"].removeprefix("artifacts/") for case in self.content["cases"] if case.get("artifact_kind") == "failure"}

        def observed(root, relative, scan_text=True):
            if relative.endswith("run-metadata.json"):
                bounded_metadata.append(relative)
                self.assertEqual(scan_text, relative in pinned_failure_metadata)  # Raw failure downloads additionally require explicit reviewed hashes.
            return original(root, relative, scan_text)

        with patch.object(builder, "safe_read", side_effect=observed):
            builder.package_files()
        expected = sum((PROJECT / "examples" / case["id"] / "run-metadata.json").is_file() for case in self.content["cases"]) + len(pinned_failure_metadata)
        self.assertEqual(len(bounded_metadata), expected)
        audit = json.loads(self.files["document-link-audit.json"])
        self.assertEqual(audit["missing_targets"], self.content["document_link_gaps"])
        self.assertTrue(all(entry["document"] in self.files and entry["unavailable_package_target"] not in self.files for entry in audit["missing_targets"]))

    def test_dataset_preflight_refuses_oversized_input_before_workspace(self):
        preflight = {"showcase/cases.json": (PROJECT / "showcase/cases.json").read_bytes()}
        preflight.update({"showcase/" + name: self.files[name] for name in ("index.html", "styles.css", "app.js")})
        preflight.update({name.removeprefix("artifacts/"): raw for name, raw in self.files.items()
                          if name.startswith("artifacts/data/") or name.removeprefix("artifacts/") in builder.DOCUMENTS})
        limit = max(map(len, preflight.values())) + 1
        for relative in ("data/records.csv", "data/manifest.json", "data/documents/riverwatch_dependency_review.txt"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                project = Path(temporary).resolve()
                for name, raw in preflight.items():
                    path = project / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                (project / relative).write_bytes(b"x" * (limit + 1))
                with patch.object(builder, "MAX_FILE_BYTES", limit), patch.object(builder, "Workspace") as workspace:
                    with self.assertRaisesRegex(ValueError, "oversized: " + re.escape(relative)):
                        builder.package_files(project)
                    workspace.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run-metadata.json"
            path.write_bytes(b"12345")
            with patch.object(builder, "MAX_FILE_BYTES", 4):
                with self.assertRaisesRegex(ValueError, "oversized"):
                    builder.safe_read(path.parent, path.name, scan_text=False)

    def test_total_package_limit_refuses_before_workspace(self):
        with patch.object(builder, "MAX_PACKAGE_BYTES", 1), patch.object(builder, "Workspace") as workspace:
            with self.assertRaisesRegex(ValueError, "package exceeds"):
                builder.package_files()
            workspace.assert_not_called()

    def test_historical_dataset_bindings_are_explicit_and_public_failure_is_separate(self):
        self.assertEqual(set(self.content["datasets"]), {"cedar-basin-synthetic-v1", "public-research-statement-pilot"})
        self.assertNotIn("evidence", self.content)
        for case in self.content["cases"]:
            if case.get("artifact_kind") == "failure":
                self.assertEqual(case["dataset_id"], "public-research-statement-pilot")
                self.assertTrue(case["dataset_binding"]["recorded_fingerprint_verified"])
                self.assertNotIn("report", case)
                continue
            self.assertEqual(case["dataset_id"], "cedar-basin-synthetic-v1")
            self.assertEqual(case["dataset_binding"]["recorded_fingerprint_verified"], case["id"] not in builder.LEGACY_UNBOUND_CASES)

    def test_public_timeout_retains_admitted_preflight_without_analytic_result(self):
        case = next(case for case in self.content["cases"] if case["id"] == "public-nci-02")
        self.assertEqual(case["failure"]["code"], "model_timeout")
        summary = case["failure_summary"]
        self.assertEqual(summary["phase"], "report")
        self.assertEqual((summary["mcp_calls"], summary["successful_mcp_calls"], summary["full_read_calls"]), (12, 12, 8))
        context = summary["context_admission"]
        self.assertTrue(context["admitted"])
        self.assertFalse(context["exact_model_fit_verified"])
        self.assertEqual((context["prompt_tokens"], context["max_tokens"], context["safety_margin"], context["reserved_tokens"], context["token_limit"], context["remaining_tokens"]), (15363, 4096, 128, 19587, 49152, 29565))
        self.assertNotIn("report", case)
        self.assertNotIn("ledger", case)
        self.assertNotIn("source_verification", case)
        self.assertNotIn("context_admissions", case["metadata"])
        self.assertNotIn("model_responses", case["metadata"])


class DatasetBindingTests(unittest.TestCase):
    """Scripted mixed datasets only: no saved public model result or source review."""

    @classmethod
    def setUpClass(cls):
        from scripts import import_public_statements as projection
        sources, capture_bytes = projection.legacy.load_sources(PROJECT / "datasets/public-research")
        cls.public_files, _ = projection.build_dataset(sources, capture_bytes)
        cls.public_id = json.loads(cls.public_files["manifest.json"])[0]["id"]

    def write(self, project, name, raw):
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def fixture(self, project):
        from run_agent import read_dataset_metadata
        for name in builder.DOCUMENTS:
            self.write(project, name, (PROJECT / name).read_bytes())
        for name in ("index.html", "app.js", "styles.css"):
            self.write(project, "showcase/" + name, (PROJECT / "showcase" / name).read_bytes())
        for name in ("evaluations/public-pilot/PROTOCOL.md", "docs/public-statements.md", "docs/evidence-catalog.md"):
            self.write(project, name, (PROJECT / name).read_bytes())
        public_root = builder.DATASETS["public-research-statement-pilot"]["root"]
        for name, raw in self.public_files.items():
            self.write(project, public_root + "/" + name, raw)
        self.write(project, "data/dataset.json", builder.encoded({"id": "cedar-basin-synthetic-v1", "kind": "synthetic", "name": "Collision fixture"}))
        self.write(project, "data/manifest.json", b"[]")
        self.write(project, "data/graph.json", builder.encoded({"nodes": [{"id": "org", "name": "Fixture org", "type": "organization", "aliases": []}], "edges": []}))
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["id", "entity_id", "title", "date", "text", "subject", "predicate", "value"])
        writer.writerow([self.public_id, "org", "Synthetic collision", "2026-01-01", "Different synthetic content", "", "", ""])
        self.write(project, "data/records.csv", stream.getvalue().encode("utf-8"))
        cases = []
        for case_id, dataset_id in (("scripted-synthetic", "cedar-basin-synthetic-v1"), ("scripted-public", "public-research-statement-pilot")):
            root = project / builder.DATASETS[dataset_id]["root"]
            workspace = builder.Workspace(root)
            try:
                record = workspace.read(self.public_id)
            finally:
                workspace.close()
            base = "examples/" + case_id + "/"
            report = {"title": "Scripted packaging fixture", "target": record["entity_ids"][0], "status": "complete", "summary": "No model run.",
                      "findings": [{"claim": "Packaging fixture only.", "evidence_ids": [record["id"]], "qualification": "No analytic acceptance."}],
                      "conflicts": [], "media_observations": [], "limitations": [], "follow_up": []}
            ledger = [{key: record[key] for key in ("id", "title", "source", "date", "sha256")}]
            ledger[0]["media_sha256"] = None
            for name, value in (("report.json", report), ("evidence-ledger.json", ledger), ("tool-trace.json", []),
                                ("run-metadata.json", {"dataset": read_dataset_metadata(root), "engine": "scripted"})):
                self.write(project, base + name, builder.encoded(value))
            for name in ("report.md", "REVIEW.md"):
                self.write(project, base + name, b"Scripted packaging fixture; no model output or acceptance.\n")
            cases.append({"id": case_id, "dataset_id": dataset_id, "review_state": "pending", "review_source": base + "REVIEW.md"})
        config = {"schema_version": 1, "default_case": "scripted-synthetic", "project_status": "Scripted only", "cases": cases}
        self.write(project, "showcase/cases.json", builder.encoded(config))
        return config

    def test_colliding_ids_stay_with_each_dataset_and_exact_public_projection(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            self.fixture(project)
            files = builder.package_files(project)
            content = json.loads(files["content.json"])
            synthetic = content["datasets"]["cedar-basin-synthetic-v1"]["evidence"][self.public_id]
            public = content["datasets"]["public-research-statement-pilot"]["evidence"][self.public_id]
            self.assertNotEqual(synthetic["text"], public["text"])
            self.assertTrue(synthetic["file_url"].startswith("artifacts/data/"))
            self.assertTrue(public["file_url"].startswith("artifacts/datasets/public-research/imported-statements/"))
            for name, raw in self.public_files.items():
                self.assertEqual(files["artifacts/datasets/public-research/imported-statements/" + name], raw)
            self.assertTrue(all(case["dataset_binding"]["recorded_fingerprint_verified"] for case in content["cases"]))
            self.assertIn("not relationship validity", content["datasets"]["public-research-statement-pilot"]["note"])
            self.assertNotIn("content.evidence", files["app.js"].decode())

    def test_mismatched_recorded_dataset_hash_files_and_identity_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            self.fixture(project)
            name = project / "examples/scripted-public/run-metadata.json"
            original = json.loads(name.read_bytes())
            for key, bad in (("sha256", "0" * 64), ("files", {}), ("id", "cedar-basin-synthetic-v1"), ("kind", "synthetic")):
                with self.subTest(key=key):
                    altered = json.loads(json.dumps(original))
                    altered["dataset"][key] = bad
                    name.write_bytes(builder.encoded(altered))
                    with self.assertRaisesRegex(ValueError, "dataset fingerprint differs"):
                        builder.package_files(project)
            name.write_bytes(builder.encoded({}))
            with self.assertRaisesRegex(ValueError, "required dataset fingerprint"):
                builder.package_files(project)

    def test_dataset_key_and_manifest_path_escape_refused_before_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            config = self.fixture(project)
            config["cases"][0]["dataset_id"] = "../other-project"
            self.write(project, "showcase/cases.json", builder.encoded(config))
            with patch.object(builder, "Workspace") as workspace:
                with self.assertRaisesRegex(ValueError, "allowlisted dataset_id"):
                    builder.package_files(project)
                workspace.assert_not_called()
            config["cases"][0]["dataset_id"] = "cedar-basin-synthetic-v1"
            self.write(project, "showcase/cases.json", builder.encoded(config))
            self.write(project, "data/manifest.json", builder.encoded([{"path": "../outside.txt"}]))
            with patch.object(builder, "Workspace") as workspace:
                with self.assertRaisesRegex(ValueError, "contained relative"):
                    builder.package_files(project)
                workspace.assert_not_called()

    def test_public_tampering_and_unlisted_provenance_files_refused_or_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            self.fixture(project)
            root = builder.DATASETS["public-research-statement-pilot"]["root"]
            extra = root + "/sources/private-notes.txt"
            self.write(project, extra, b"Not a captured input; never publish.")
            self.assertNotIn("artifacts/" + extra, builder.package_files(project))
            name = next(name for name in self.public_files if name.startswith("evidence/"))
            self.write(project, root + "/" + name, b"changed source")
            with self.assertRaisesRegex(ValueError, "differs from verified offline reproduction"):
                builder.package_files(project)

    def test_legacy_fingerprint_exception_is_not_available_to_new_or_public_cases(self):
        minimal = {"id": "cedar-basin-synthetic-v1"}
        self.assertFalse(builder.bind_dataset({}, minimal, "cbri")["recorded_fingerprint_verified"])
        for case_id, dataset in (("new-case", minimal), ("cbri", {"id": "public-research-statement-pilot"})):
            with self.subTest(case_id=case_id, dataset=dataset):
                with self.assertRaisesRegex(ValueError, "required dataset fingerprint"):
                    builder.bind_dataset({}, dataset, case_id)

    def test_dataset_protocol_links_copy_exact_allowlisted_documents(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            self.fixture(project)
            files = builder.package_files(project)
            content = json.loads(files["content.json"])
            expected = {"cedar-basin-synthetic-v1": "evaluations/local-pilot/REVIEW-PROTOCOL.md",
                        "public-research-statement-pilot": "evaluations/public-pilot/PROTOCOL.md"}
            for case in content["cases"]:
                dataset = content["datasets"][case["dataset_id"]]
                relative = expected[case["dataset_id"]]
                self.assertEqual(dataset["review_protocol_url"], "artifacts/" + relative)
                self.assertEqual(files[dataset["review_protocol_url"]], (project / relative).read_bytes())
            self.assertIn('["Review protocol", datasetForCase().review_protocol_url]', files["app.js"].decode())

    def test_saved_retrieval_profile_is_narrowly_published_without_context_bodies(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            self.fixture(project)
            path = project / "examples/scripted-public/run-metadata.json"
            metadata = json.loads(path.read_bytes())
            metadata.update(engine="local", retrieval_profile="catalog", context_admissions=[{"rendered_prompt": "PRIVATE_CONTEXT_SENTINEL"}],
                            workflow_coverage={"source_body": "PRIVATE_CONTEXT_SENTINEL"})
            path.write_bytes(builder.encoded(metadata))
            files = builder.package_files(project)
            content = json.loads(files["content.json"])
            case = next(case for case in content["cases"] if case["id"] == "scripted-public")
            self.assertEqual(case["metadata"]["retrieval_profile"], "catalog")
            self.assertEqual(case["metadata"]["engine"], "local")
            self.assertNotIn("context_admissions", case["metadata"])
            self.assertNotIn("workflow_coverage", case["metadata"])
            self.assertNotIn(b"PRIVATE_CONTEXT_SENTINEL", b"".join(files.values()))
            metadata["retrieval_profile"] = "arbitrary-profile"
            path.write_bytes(builder.encoded(metadata))
            with self.assertRaisesRegex(ValueError, "Unsupported saved retrieval profile"):
                builder.package_files(project)


class FailureCaseTests(unittest.TestCase):
    """Preserved real failure plus temporary negative fixtures; never a model run."""
    write = DatasetBindingTests.write
    fixture = DatasetBindingTests.fixture

    @classmethod
    def setUpClass(cls):
        DatasetBindingTests.setUpClass.__func__(cls)

    def failure_fixture(self, project):
        self.fixture(project)
        definition = next(case for case in json.loads((PROJECT / "showcase/cases.json").read_bytes())["cases"] if case.get("artifact_kind") == "failure")
        base = "evaluations/public-pilot/" + definition["id"] + "/"
        for name in ("failure.json", "run-metadata.json", "tool-trace.json", "REVIEW.md"):
            self.write(project, base + name, (PROJECT / base / name).read_bytes())
        config = {"schema_version": 1, "default_case": definition["id"], "project_status": "Packaging test only", "cases": [definition]}
        self.write(project, "showcase/cases.json", builder.encoded(config))
        return config, base

    def test_failure_preserves_originals_without_report_or_ledger_and_limits_display_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            config, base = self.failure_fixture(project)
            files = builder.package_files(project)
            case = json.loads(files["content.json"])["cases"][0]
            self.assertNotIn("report", case)
            self.assertNotIn("ledger", case)
            self.assertNotIn("report.json", case["artifacts"])
            self.assertNotIn("evidence-ledger.json", case["artifacts"])
            for name in ("failure.json", "run-metadata.json", "tool-trace.json", "REVIEW.md"):
                self.assertEqual(files[case["artifacts"][name]], (PROJECT / base / name).read_bytes())
            summary = case["failure_summary"]
            self.assertEqual((summary["mcp_calls"], summary["successful_mcp_calls"], summary["full_read_calls"]), (9, 8, 5))
            self.assertEqual(len(summary["recorded_retrieved_ids"]), 5)
            context = summary["context_admission"]
            self.assertEqual((context["prompt_tokens"], context["reserved_tokens"], context["token_limit"]), (16823, 17463, 16384))
            self.assertLessEqual(context.keys(), {"policy", "admitted", "exact_model_fit_verified", "step", "token_limit", "safety_margin", "max_tokens", "prompt_tokens", "reserved_tokens", "remaining_tokens", "generation_request_bytes", "max_request_bytes", "rendered_prompt_bytes", "canonical_request_sha256", "rendered_prompt_sha256"})
            self.assertNotIn("context_admissions", case["metadata"])
            self.assertNotIn("model_responses", case["metadata"])

    def test_present_report_or_ledger_cannot_be_hidden_as_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            _, base = self.failure_fixture(project)
            for name in ("report.json", "report.md", "evidence-ledger.json"):
                path = project / base / name
                path.write_bytes(b"existing output")
                with self.assertRaisesRegex(ValueError, "contains a report or final ledger"):
                    builder.package_files(project)
                path.unlink()

    def test_scripted_report_timeout_accepts_admitted_context_without_inventing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            config, base = self.failure_fixture(project)
            metadata = json.loads((project / base / "run-metadata.json").read_bytes())
            metadata["phase"] = "report"
            metadata["context_admissions"] = [{**metadata["context_admissions"][-1],
                "phase": "report", "admitted": True, "prompt_tokens": 100, "max_tokens": 200, "safety_margin": 128,
                "reserved_tokens": 428, "token_limit": 1024, "remaining_tokens": 596,
                "private_context_body": "DO_NOT_DISPLAY_SCRIPTED_CONTEXT"}]
            raw = builder.encoded(metadata)
            self.write(project, base + "run-metadata.json", raw)
            self.write(project, base + "failure.json", builder.encoded({"code": "model_timeout", "message": "Scripted timeout; no model invoked."}))
            self.write(project, base + "REVIEW.md", b"Scripted packaging fixture only; no analytic output.\n")
            config["cases"][0]["metadata_sha256"] = builder.digest(raw)
            self.write(project, "showcase/cases.json", builder.encoded(config))
            files = builder.package_files(project)
            case = json.loads(files["content.json"])["cases"][0]
            self.assertEqual(case["failure"]["code"], "model_timeout")
            self.assertEqual(case["failure_summary"]["phase"], "report")
            self.assertTrue(case["failure_summary"]["context_admission"]["admitted"])
            self.assertEqual(case["failure_summary"]["context_admission"]["remaining_tokens"], 596)
            self.assertNotIn("private_context_body", case["failure_summary"]["context_admission"])
            self.assertNotIn("report", case)
            self.assertNotIn("ledger", case)
            self.assertNotIn(b"DO_NOT_DISPLAY_SCRIPTED_CONTEXT", files["content.json"])

    def test_metadata_is_required_and_original_hash_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            _, base = self.failure_fixture(project)
            path = project / base / "run-metadata.json"
            original = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(ValueError, "missing or oversized"):
                builder.package_files(project)
            path.write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "explicit reviewed hash"):
                builder.package_files(project)

    def test_failure_config_path_escape_and_nonpublic_roots_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            config, _ = self.failure_fixture(project)
            original = dict(config["cases"][0])
            for change, error in (({"artifact_root": "../runs/public-nci-01"}, "Configurable failure artifact paths"),
                                  ({"review_source": "evaluations/local-pilot/REVIEW-PROTOCOL.md"}, "exact public-pilot artifact root"),
                                  ({"id": "../runs/public-nci-01"}, "Invalid case ID"),
                                  ({"id": "local-nci-01"}, "limited public-pilot")):
                config["cases"][0] = {**original, **change}
                config["default_case"] = config["cases"][0]["id"]
                self.write(project, "showcase/cases.json", builder.encoded(config))
                with self.assertRaisesRegex(ValueError, error):
                    builder.package_files(project)

    def test_failure_metadata_binding_status_counts_and_overflow_must_be_consistent(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            config, base = self.failure_fixture(project)
            path = project / base / "run-metadata.json"
            original = json.loads(path.read_bytes())
            changes = [("status", "complete", "failed local catalog"),
                       ("dataset", {**original["dataset"], "sha256": "0" * 64}, "dataset fingerprint differs"),
                       ("retrieved_evidence_ids", [], "Recorded retrieved IDs disagree"),
                       ("context_admissions", [{**original["context_admissions"][-1], "remaining_tokens": -1}], "consistent recorded overflow"),
                       ("context_admissions", [{**original["context_admissions"][-1], "prompt_tokens": True}], "bounded context-admission metric")]
            for key, value, error in changes:
                with self.subTest(key=key, error=error):
                    raw = builder.encoded({**original, key: value})
                    path.write_bytes(raw)
                    # A changed explicit test pin allows the separate content guard to be exercised.
                    config["cases"][0]["metadata_sha256"] = builder.digest(raw)
                    self.write(project, "showcase/cases.json", builder.encoded(config))
                    with self.assertRaisesRegex(ValueError, error):
                        builder.package_files(project)


@unittest.skipUnless(os.name == "nt", "Windows junction regression requires Windows")
class ShowcaseJunctionTests(unittest.TestCase):
    @contextmanager
    def junction(self, root, link, target):
        root = root.resolve()
        target.mkdir(parents=True, exist_ok=True)
        self.assertTrue(link.parent.resolve().is_relative_to(root))
        self.assertTrue(target.resolve().is_relative_to(root))
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        command = "$ErrorActionPreference = 'Stop'\nNew-Item -ItemType Junction -Path " + quote(link) + " -Target " + quote(target) + " | Out-Null"
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        try:
            try:
                result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], capture_output=True, timeout=20)
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.skipTest("Could not create a Windows junction: " + type(exc).__name__)
            if result.returncode:
                self.skipTest("Windows junction creation unavailable")
            self.assertEqual(getattr(link.lstat(), "st_reparse_tag", None), 0xA0000003)
            yield link
        finally:
            # Remove only the junction, after checking lexical parent and resolved target.
            if builder.linked(link):
                self.assertTrue(link.parent.resolve().is_relative_to(root))
                self.assertTrue(link.resolve().is_relative_to(root))
                self.assertEqual(getattr(link.lstat(), "st_reparse_tag", None), 0xA0000003)
                link.rmdir()

    def test_source_ancestor_and_root_junctions_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual"
            actual.mkdir()
            (actual / "example.txt").write_text("fixture", encoding="utf-8")
            with self.junction(root, root / "alias", actual) as alias:
                with self.assertRaisesRegex(ValueError, "Linked path component"):
                    builder.safe_read(root, "alias/example.txt")
                with self.assertRaisesRegex(ValueError, "Linked path component"):
                    builder.safe_read(alias, "example.txt")
            self.assertEqual((actual / "example.txt").read_text(), "fixture")

    def test_output_ancestor_and_root_junctions_never_write_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual-output"
            output = actual / "owned"
            old = {"index.html": b"old", "content.json": b'{"cases": []}'}
            new = {**old, "index.html": b"new"}
            with patch.object(builder, "package_files", return_value=old):
                builder.build(output)
            with self.junction(root, root / "alias", actual) as alias:
                with patch.object(builder, "package_files", return_value=new):
                    with self.assertRaisesRegex(ValueError, "Linked path component"):
                        builder.build(alias / "owned", refresh=True)
                    with self.assertRaisesRegex(ValueError, "Linked path component"):
                        builder.build(alias / "fresh")
                    with self.assertRaisesRegex(ValueError, "Linked path component"):
                        builder.build(alias, refresh=True)
                self.assertEqual((output / "index.html").read_bytes(), b"old")
                self.assertFalse((actual / "fresh").exists())

    def test_junction_inside_owned_output_rejected_before_refresh(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "owned"
            files = {"index.html": b"original", "content.json": b'{"cases": []}'}
            with patch.object(builder, "package_files", return_value=files):
                builder.build(output)
            with self.junction(root, output / "unexpected-link", root / "foreign"):
                with patch.object(builder, "package_files", return_value={**files, "index.html": b"changed"}):
                    with self.assertRaisesRegex(ValueError, "Linked path component"):
                        builder.build(output, refresh=True)
                self.assertEqual((output / "index.html").read_bytes(), b"original")


class GroundedArtifactTests(unittest.TestCase):
    """Scripted artifact-contract checks; no model run or analytic acceptance claimed."""
    def fixture(self):
        trace = [{"name": "read_media", "status": "completed", "args": {"evidence_id": "image-source"}},
                 {"name": "read_media", "status": "completed", "args": {"evidence_id": "video-source", "timestamps": [14.5, 29]}}]
        image = [{"evidence_id": "image-source", "locator": "image", "observation": "Visible caption."}]
        video = [{"evidence_id": "video-source", "locator": "00:15", "observation": "Ready is not established."},
                 {"evidence_id": "video-source", "locator": "00:29", "observation": "Second visible caption."}]
        outputs, records = {}, []
        for number, observations in enumerate((image, video), 1):
            path = f"media-observation-{number:02d}.json"
            raw = json.dumps({"media_observations": observations}, ensure_ascii=False, separators=(",", ":")).encode()
            outputs[path] = raw
            records.append({"call": number, "evidence_id": observations[0]["evidence_id"], "locators": [item["locator"] for item in observations],
                            "path": path, "status": "observed", "input_sha256": "a" * 64, "output_sha256": builder.digest(raw),
                            "private_context": "never-publish-this-context"})
        # An unsuccessful artifact must neither be opened nor enter the published summary.
        records.insert(0, {"status": "rejected", "path": "media-observation-99.json", "reason": "never-publish-this-reason"})
        metadata = {"grounded_media": {"enabled": True, "policy": "deferred-isolated-pixels-v1", "constrained_fields": ["follow_up", "limitations", "media_observations"],
                                       "observations": records, "messages": "never-publish-these-messages"}}
        return metadata, {"media_observations": image + video, "follow_up": []}, trace, outputs

    def test_successful_lineage_is_filtered_exact_and_byte_preserving(self):
        metadata, report, trace, outputs = self.fixture()
        summary, copied = builder.grounded_observation_artifacts(metadata, report, trace, outputs.__getitem__)
        self.assertEqual(copied, outputs)
        self.assertEqual([item["call"] for item in summary["observations"]], [1, 2])
        self.assertEqual(summary["observations"][1]["locators"], ["00:15", "00:29"])
        self.assertTrue(summary["output_hashes_verified"] and summary["final_observations_match"])
        self.assertNotIn("never-publish", json.dumps(summary))
        self.assertNotIn("observation", summary["observations"][0])

    def test_hash_lineage_paths_schema_and_final_reuse_must_match(self):
        mutations = [
            lambda m, r, t, o: m["grounded_media"]["observations"][1].update(output_sha256="b" * 64),
            lambda m, r, t, o: m["grounded_media"]["observations"][1].update(call=2),
            lambda m, r, t, o: m["grounded_media"]["observations"][1].update(evidence_id="wrong-source"),
            lambda m, r, t, o: m["grounded_media"]["observations"][2].update(locators=["00:29", "00:15"]),
            lambda m, r, t, o: m["grounded_media"]["observations"][2].update(locators=["data:image/png;base64,not-a-locator", "00:29"]),
            lambda m, r, t, o: m["grounded_media"]["observations"][1].update(path="../media-observation-01.json"),
            lambda m, r, t, o: r["media_observations"][0].update(observation="Rewritten final observation."),
            lambda m, r, t, o: r["media_observations"].reverse(),
            lambda m, r, t, o: m["grounded_media"]["observations"].pop(),
            lambda m, r, t, o: t[0].update(status="failed"),
            lambda m, r, t, o: r.update(follow_up=["Invented recommendation"]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                metadata, report, trace, outputs = self.fixture()
                mutate(metadata, report, trace, outputs)
                with self.assertRaises(ValueError):
                    builder.grounded_observation_artifacts(metadata, report, trace, outputs.__getitem__)
        metadata, report, trace, outputs = self.fixture()
        invalid = builder.encoded({"media_observations": report["media_observations"][:1], "reasoning": "never-publish"})
        outputs["media-observation-01.json"] = invalid
        metadata["grounded_media"]["observations"][1]["output_sha256"] = builder.digest(invalid)
        with self.assertRaisesRegex(ValueError, "output fields"):
            builder.grounded_observation_artifacts(metadata, report, trace, outputs.__getitem__)
        metadata, report, trace, outputs = self.fixture()
        duplicate = outputs["media-observation-01.json"].replace(b'{"media_observations":', b'{"media_observations":"private-hidden-value","media_observations":', 1)
        outputs["media-observation-01.json"] = duplicate
        metadata["grounded_media"]["observations"][1]["output_sha256"] = builder.digest(duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate isolated"):
            builder.grounded_observation_artifacts(metadata, report, trace, outputs.__getitem__)

    def test_packager_exposes_only_verified_original_observation_files(self):
        # Inject a scripted artifact contract in memory; never alter/publish a real example.
        case_id = "local-riverwatch-thinking-rejected"
        base = f"examples/{case_id}/"
        original = builder.safe_read
        report = json.loads(original(PROJECT, base + "report.json"))
        trace = json.loads(original(PROJECT, base + "tool-trace.json"))
        metadata = json.loads(original(PROJECT, base + "run-metadata.json", scan_text=False))
        output_files, records = {}, []
        ordered = []
        for call_number, call in enumerate(trace, 1):
            if call["name"] != "read_media" or call["status"] != "completed":
                continue
            evidence_id = call["args"]["evidence_id"]
            items = [item for item in report["media_observations"] if item["evidence_id"] == evidence_id]
            ordered.extend(items)
            name = f"media-observation-{len(records) + 1:02d}.json"
            raw = builder.encoded({"media_observations": items})
            output_files[name] = raw
            records.append({"call": call_number, "evidence_id": evidence_id, "locators": [item["locator"] for item in items], "path": name,
                            "status": "observed", "input_sha256": "a" * 64, "output_sha256": builder.digest(raw)})
        report["media_observations"], report["follow_up"] = ordered, []
        metadata["grounded_media"] = {"enabled": True, "policy": "deferred-isolated-pixels-v1", "observations": records,
                                      "constrained_fields": ["follow_up", "limitations", "media_observations"], "reasoning": "never-publish-this-sentinel"}

        def scripted(root, relative, scan_text=True):
            if relative == base + "run-metadata.json":
                return builder.encoded(metadata)
            if relative == base + "report.json":
                return builder.encoded(report)
            if relative.startswith(base) and relative[len(base):] in output_files:
                return output_files[relative[len(base):]]
            return original(root, relative, scan_text)

        with patch.object(builder, "safe_read", side_effect=scripted):
            files = builder.package_files()
        case = next(item for item in json.loads(files["content.json"])["cases"] if item["id"] == case_id)
        for record in records:
            self.assertEqual(files[case["artifacts"][record["path"]]], output_files[record["path"]])
        published = files[case["artifacts"]["run_summary"]]
        self.assertIn(b'"grounded_media"', published)
        self.assertNotIn(b"never-publish", published)
        self.assertNotIn(b'"observation":', published)


class CompactSynthesisTests(unittest.TestCase):
    """Scripted publishing checks, not a reconstructed report request or model run."""
    def fixture(self):
        return {"compact_synthesis": {"enabled": True, "private_context": "never-publish", "generations": [{
            "step": 23, "policy": "exact-record-compact-synthesis-v1", "input_scope": "canonical_report_messages_only",
            "input_sha256": "a" * 64, "input_bytes": 19000,
            "counts": {"mcp_calls": 17, "evidence_occurrences": 18, "evidence_records": 9,
                       "duplicate_evidence_records": 9, "omitted_raw_image_blocks": 4,
                       "identity_graph_results": 2, "tool_failures": 0, "extra_context": "never-publish"},
            "evidence_lineage": [{"text": "never-publish"}], "identity_graph_lineage": [{"result": "never-publish"}],
            "messages": "never-publish", "settings": "never-publish", "reasoning": "never-publish", "base64": "never-publish"
        }]}}

    def test_compact_metrics_filter_private_fields_and_refuse_invalid_scope(self):
        summary = builder.compact_synthesis_summary(self.fixture())
        self.assertEqual(set(summary), {"enabled", "generations"})
        self.assertEqual(set(summary["generations"][0]), {"step", "policy", "input_scope", "input_sha256", "input_bytes", "counts"})
        self.assertNotIn("never-publish", json.dumps(summary))
        self.assertIsNone(builder.compact_synthesis_summary({}))
        self.assertIsNone(builder.compact_synthesis_summary({"compact_synthesis": {"enabled": False}}))
        mutations = [
            lambda g: g.update(policy="unknown"),
            lambda g: g.update(input_scope="full_http_request"),
            lambda g: g.update(input_sha256="not-a-fingerprint"),
            lambda g: g.update(input_bytes=True),
            lambda g: g.update(step=0),
            lambda g: g["counts"].update(tool_failures=-1),
            lambda g: g["counts"].update(evidence_occurrences=99),
            lambda g: g["counts"].update(mcp_calls="17")
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                metadata = self.fixture()
                mutate(metadata["compact_synthesis"]["generations"][0])
                with self.assertRaises(ValueError):
                    builder.compact_synthesis_summary(metadata)

    def test_compact_package_extract_requires_grounding_and_preserves_originals(self):
        # Add recorded-metric fixtures in memory only; selected real cases stay unchanged.
        original = builder.safe_read
        case_id = "local-riverwatch-grounded-rejected"
        def scripted(root, relative, scan_text=True):
            raw = original(root, relative, scan_text)
            if relative == f"examples/{case_id}/run-metadata.json":
                metadata = json.loads(raw)
                metadata.update(self.fixture())
                return builder.encoded(metadata)
            return raw
        with patch.object(builder, "safe_read", side_effect=scripted):
            files = builder.package_files()
        case = next(item for item in json.loads(files["content.json"])["cases"] if item["id"] == case_id)
        self.assertEqual(case["metadata"]["compact_synthesis"], builder.compact_synthesis_summary(self.fixture()))
        self.assertNotIn(b"never-publish", files[case["artifacts"]["run_summary"]])
        self.assertEqual(files[case["artifacts"]["report.json"]], original(PROJECT, f"examples/{case_id}/report.json"))
        case_id = "local-delta"
        with patch.object(builder, "safe_read", side_effect=scripted):
            with self.assertRaisesRegex(ValueError, "requires verified grounded"):
                builder.package_files()


class EvidenceSummaryTests(unittest.TestCase):
    def fixture(self, summary="Host overview with supplied assertions; disagreements remain unresolved."):
        raw = summary.encode("utf-8")
        metadata = {"evidence_summary": {"enabled": True, "policy": "exact-assertion-evidence-overview-v1",
            "scope": "complete_reports_only", "private_context": "never-publish", "generations": [{
                "step": 23, "status": "complete", "attribution": "host_constructed",
                "summary_sha256": builder.digest(raw), "summary_bytes": len(raw),
                "counts": {"source_ids": 9, "record_versions": 9, "comparable_assertions": 9,
                           "ignored_assertions": 0, "records_without_assertions": 0, "differing_groups": 2,
                           "private_count": "never-publish"},
                "source_lineage": [{"record_index": 1, "evidence_id": "never-publish"}],
                "candidate_groups": [{"assertion_refs": "never-publish"}], "summary": "never-publish",
                "messages": "never-publish", "reasoning": "never-publish", "base64": "never-publish"
            }]}}
        return metadata, {"status": "complete", "summary": summary}

    def test_summary_fingerprint_and_attribution_are_checked_without_publishing_lineage(self):
        metadata, report = self.fixture("Supplied claim: café; unresolved.")
        published = builder.evidence_summary_metadata(metadata, report)
        self.assertTrue(published["final_summary_constrained"])
        self.assertTrue(published["final_summary_hash_verified"])
        self.assertNotIn("never-publish", json.dumps(published))
        self.assertEqual(set(published["generations"][0]),
                         {"step", "status", "attribution", "summary_sha256", "summary_bytes", "counts"})
        with self.assertRaisesRegex(ValueError, "differs"):
            builder.evidence_summary_metadata(metadata, {**report, "summary": report["summary"] + "changed"})
        for field, value in (("policy", "unknown"), ("scope", "all_reports")):
            changed, report = self.fixture()
            changed["evidence_summary"][field] = value
            with self.assertRaises(ValueError):
                builder.evidence_summary_metadata(changed, report)
        for field, value in (("attribution", "model_authored"), ("summary_bytes", True), ("summary_sha256", "invalid")):
            changed, report = self.fixture()
            changed["evidence_summary"]["generations"][0][field] = value
            with self.assertRaises(ValueError):
                builder.evidence_summary_metadata(changed, report)

    def test_incomplete_final_report_does_not_inherit_prior_host_summary_attribution(self):
        metadata, _ = self.fixture()
        report = {"status": "insufficient_evidence", "summary": "Model-authored bounded abstention."}
        published = builder.evidence_summary_metadata(metadata, report)
        self.assertFalse(published["final_summary_constrained"])
        self.assertFalse(published["final_summary_hash_verified"])
        self.assertEqual(len(published["generations"]), 1)
        metadata["evidence_summary"]["generations"] = []
        self.assertEqual(builder.evidence_summary_metadata(metadata, report)["generations"], [])
        with self.assertRaisesRegex(ValueError, "lacks construction"):
            builder.evidence_summary_metadata(metadata, {**report, "status": "complete"})

    def test_summary_constraint_requires_matching_declared_host_construction(self):
        metadata, report, trace, outputs = GroundedArtifactTests().fixture()
        summary_metadata, summary_report = self.fixture()
        metadata.update(summary_metadata)
        report.update(summary_report)
        with self.assertRaisesRegex(ValueError, "constrained fields"):
            builder.grounded_observation_artifacts(metadata, report, trace, outputs.__getitem__)
        metadata["grounded_media"]["constrained_fields"].append("summary")
        published, copied = builder.grounded_observation_artifacts(metadata, report, trace, outputs.__getitem__)
        self.assertIn("summary", published["constrained_fields"])
        self.assertEqual(copied, outputs)
        del metadata["evidence_summary"]
        with self.assertRaisesRegex(ValueError, "constrained fields"):
            builder.grounded_observation_artifacts(metadata, report, trace, outputs.__getitem__)


if __name__ == "__main__":
    unittest.main()

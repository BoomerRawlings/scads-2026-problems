import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from analytics311.errors import AnalyticsError
from analytics311.resources import ASSETS, asset_path, default_config_path, load_profile


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_release", ROOT / "tools/build_release.py")
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


class DistributionTests(unittest.TestCase):
    def test_bundled_default_reads_assets_but_writes_to_caller_workspace(self):
        before = {name: hashlib.sha256(asset_path(name).read_bytes()).hexdigest() for name in ASSETS}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path, profile = load_profile(workdir=directory)
            self.assertEqual(path, default_config_path())
            self.assertEqual(Path(profile["runs_dir"]), Path(directory).resolve() / "runs")
            self.assertFalse(Path(profile["runs_dir"]).exists())
            for key in ("fixture_path", "manifest_path", "catalog_path"):
                self.assertTrue(Path(profile[key]).is_file())
                self.assertFalse(Path(profile[key]).is_relative_to(Path(directory)))
        self.assertEqual(before, {name: hashlib.sha256(asset_path(name).read_bytes()).hexdigest() for name in ASSETS})

    def test_explicit_packaged_profile_keeps_outputs_local(self):
        with tempfile.TemporaryDirectory() as directory:
            _, profile = load_profile(default_config_path(), workdir=directory)
            self.assertEqual(Path(profile["runs_dir"]), Path(directory).resolve() / "runs")

    def test_custom_profile_and_environment_keep_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "custom.json"
            path.write_text(json.dumps({"backend": "fixture", "fixture_path": "requests.jsonl",
                                        "runs_dir": "results"}), encoding="utf-8")
            with patch.dict(os.environ, {"ANALYTICS311_CONFIG": str(path)}):
                selected, profile = load_profile(workdir=root / "elsewhere")
            self.assertEqual(selected, path)
            self.assertEqual(Path(profile["fixture_path"]), root / "requests.jsonl")
            self.assertEqual(Path(profile["runs_dir"]), root / "results")

    def test_explicit_profile_precedes_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"ANALYTICS311_CONFIG": "missing.json"}):
            self.assertEqual(load_profile(default_config_path(), workdir=directory)[0], default_config_path())

    def test_malformed_profiles_are_typed_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profile.json"
            for contents in ("[]", "null", "{", '{"runs_dir": null}'):
                profile.write_text(contents, encoding="utf-8")
                with self.subTest(contents=contents), self.assertRaises(AnalyticsError) as failure:
                    load_profile(profile)
                self.assertEqual(failure.exception.code, "invalid_configuration")

    def test_resource_allowlist_rejects_traversal(self):
        for name in ("../config/catalog.json", "config/../../pyproject.toml", "/config/catalog.json", "unknown"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                asset_path(name)

    def test_compatibility_assets_match_bundled_bytes(self):
        self.assertEqual(set(release.verify_assets()), set(ASSETS))

    def test_build_refuses_stale_asset_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ASSETS:
                for path in (root / name, root / "analytics311/assets" / name):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(asset_path(name).read_bytes())
            (root / "config/catalog.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "catalog.json"):
                release.verify_assets(root)

    def test_cli_environment_drops_checkout_and_profile_overrides(self):
        with patch.dict(os.environ, {"PYTHONPATH": "checkout", "PYTHONHOME": "custom", "ANALYTICS311_CONFIG": "private.json", "PIP_TARGET": "elsewhere",
                                     "PIP_FIND_LINKS": "private-wheels", "PIP_INDEX_URL": "private-index", "PIP_CONSTRAINT": "custom.txt"}):
            env = release.clean_environment()
        for key in ("PYTHONPATH", "PYTHONHOME", "ANALYTICS311_CONFIG", "PIP_TARGET", "PIP_FIND_LINKS", "PIP_INDEX_URL", "PIP_CONSTRAINT"):
            self.assertNotIn(key, env)
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_smoke_cleanup_retries_transient_windows_executable_lock(self):
        with patch.object(release.tempfile, "TemporaryDirectory") as temporary, patch.object(release.time, "sleep") as sleep:
            temporary.return_value.name = str(Path(tempfile.gettempdir()) / "analytics311-install-test")
            temporary.return_value.cleanup.side_effect = [PermissionError("executable locked"), None]
            with release.temporary_directory("analytics311-install-") as name:
                self.assertEqual(name, temporary.return_value.name)
            self.assertEqual(temporary.return_value.cleanup.call_count, 2)
            sleep.assert_called_once_with(.1)

    def test_extras_are_explicit_allowlisted_and_stable(self):
        self.assertEqual((), release.normalize_extras())
        self.assertEqual(("geo", "mcp"), release.normalize_extras("mcp,geo,mcp"))
        for extras in ("model", "mcp,", ["--index-url"], "MCP"):
            with self.subTest(extras=extras), self.assertRaises(ValueError):
                release.normalize_extras(extras)

    def test_dependency_budget_includes_incomplete_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            downloaded, incomplete = target / "wheels", target / "temporary"
            downloaded.mkdir(); incomplete.mkdir()
            (downloaded / "dependency.whl").write_bytes(b"1234")
            (incomplete / "download.tmp").write_bytes(b"567890")
            with patch.object(release, "MAX_DEPENDENCY_BYTES", 10):
                release.enforce_dependency_budget(downloaded, incomplete)
            with patch.object(release, "MAX_DEPENDENCY_BYTES", 9), self.assertRaisesRegex(RuntimeError, "budget"):
                release.enforce_dependency_budget(downloaded, incomplete)

    def test_wheel_manifest_records_native_compatibility_tags_without_machine_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "native-1.0-cp312-cp312-win_arm64.whl"
            wheel.write_bytes(b"wheel")
            result = release.artifact_description(wheel, Path("dependencies") / wheel.name)
            self.assertEqual({"python": "cp312", "abi": "cp312", "platform": "win_arm64"}, result["wheel_tags"])
            self.assertEqual("dependencies/" + wheel.name, result["file"])
            self.assertNotIn(directory, json.dumps(result))
            target = release.target_description()
            self.assertEqual(sys.implementation.cache_tag, target["python_cache_tag"])
            self.assertIn("current interpreter", target["dependency_target"])

    def test_guard_allows_only_stdlib_socketpair_not_localhost_or_remote_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sitecustomize.py").write_text(release.NETWORK_GUARD, encoding="utf-8")
            env = release.clean_environment()
            env["PYTHONPATH"] = str(root)
            script = '''
import os, socket
assert os.environ.get("ANALYTICS311_OFFLINE_GUARD_ACTIVE") == "1"
first, second = socket.socketpair()
first.send(b"x")
assert second.recv(1) == b"x"
first.close(); second.close()
for operation in (lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
                  lambda: socket.getaddrinfo("127.0.0.1", 80),
                  lambda: socket.getaddrinfo("example.com", 443)):
    try: operation()
    except RuntimeError as error: assert "forbids networking" in str(error)
    else: raise AssertionError("Network operation escaped audit guard")
'''
            result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_missing_wheelhouse_is_rejected_before_dependency_process(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(release.subprocess, "Popen") as start:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "wheelhouse"):
                release.stage_dependencies(root / "project.whl", root / "dependencies",
                                           wheelhouses=[root / "missing"], no_network=True)
            start.assert_not_called()

    def test_existing_output_is_rejected_before_building_and_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(release, "verify_assets") as verify:
            output = Path(directory) / "release"
            output.mkdir()
            original = output / "old.whl"
            original.write_bytes(b"verified wheel")
            with self.assertRaisesRegex(ValueError, "already exists"):
                release.build(output)
            self.assertEqual(b"verified wheel", original.read_bytes())
            verify.assert_not_called()

    def test_release_publication_copies_inventory_and_commits_complete_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "dependency-1.0-py3-none-any.whl"
            artifact.write_bytes(b"wheel")
            output = root / "release"
            manifest = {"artifacts": [release.artifact_description(artifact, "dependencies/" + artifact.name)]}
            release.publish_release(output, [artifact], manifest)
            self.assertEqual(b"wheel", (output / "dependencies" / artifact.name).read_bytes())
            self.assertEqual(manifest, json.loads((output / "release-manifest.json").read_text()))
            self.assertIn(manifest["artifacts"][0]["sha256"], (output / "SHA256SUMS").read_text())
            self.assertFalse(list(root.glob(".analytics311-release-*")))

    def test_publication_failure_never_leaves_partial_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "dependency-1.0-py3-none-any.whl"
            artifact.write_bytes(b"verified wheel")
            manifest = {"artifacts": [release.artifact_description(artifact, artifact.name)]}
            artifact.write_bytes(b"altered wheel!")
            with self.assertRaisesRegex(RuntimeError, "changed"):
                release.publish_release(root / "release", [artifact], manifest)
            self.assertFalse((root / "release").exists())
            self.assertFalse(list(root.glob(".analytics311-release-*")))

    def test_wheel_hashing_does_not_load_entire_file(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.whl"
            artifact.write_bytes(b"wheel")
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")):
                self.assertEqual(hashlib.sha256(b"wheel").hexdigest(), release.sha256(artifact))

    def test_handoff_inventory_is_explicit_and_small(self):
        inventory = release.handoff_description()
        self.assertEqual(set(release.HANDOFF_FILES), {item["file"] for item in inventory})
        self.assertLess(sum(item["bytes"] for item in inventory), 1024 * 1024)


if __name__ == "__main__":
    unittest.main()

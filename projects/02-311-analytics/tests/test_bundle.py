import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("package_bundle", ROOT / "tools/package_bundle.py")
package = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(package)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.release, self.source = self.root / "release", self.root / "source"
        self.release.mkdir()
        self.source.mkdir()
        self.output = self.root / "bundle.zip"
        artifacts, handoff = [], []
        for directory, names, entries in (
                (self.release, ["analytics311-0.4.0-py3-none-any.whl", "dependencies/tzdata-2026.5-py2.py3-none-any.whl"], artifacts),
                (self.source, sorted(package.HANDOFF_FILES), handoff)):
            for name in names:
                content = (name + "\n").encode()
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                entries.append({"file": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        self.manifest = {"name": "analytics311", "version": "0.4.0", "requires_python": ">=3.11",
                         "install_requirement": "analytics311==0.4.0", "extras_bundled": [],
                         "verification": {"status": "passed", "handoff": {"status": "passed", "export_stress": {"status": "passed"}}}, "artifacts": artifacts, "handoff_files": handoff,
                         "target": {"python_implementation": "CPython", "python_version": "3.12.14", "python_platform": "win-amd64"}}
        self.save_manifest()

    def save_manifest(self):
        (self.release / "release-manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")
        (self.release / "SHA256SUMS").write_text("".join(f"{a['sha256']}  {a['file']}\n" for a in self.manifest["artifacts"]), encoding="utf-8", newline="\n")

    def build(self, output=None):
        return package.bundle(self.release, output or self.output, source_root=self.source)

    def test_repeat_assembly_is_byte_reproducible_and_inventory_complete(self):
        first = self.build()
        second = self.build(self.root / "second.zip")
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual(first["bytes"], second["bytes"])
        with zipfile.ZipFile(self.output) as archive:
            self.assertIsNone(archive.testzip())
            inventory = json.loads(archive.read("BUNDLE-MANIFEST.json"))["entries"]
            self.assertEqual(set(archive.namelist()) - {"BUNDLE-MANIFEST.json"}, set(inventory))
            for name, entry in inventory.items():
                self.assertEqual(entry["sha256"], hashlib.sha256(archive.read(name)).hexdigest())
            self.assertIn(b'"analytics311==0.4.0"', archive.read("INSTALL.txt"))
            self.assertIn(b"3.12.14; win-amd64", archive.read("INSTALL.txt"))

    def test_unlisted_private_files_and_corpus_are_never_bundled(self):
        (self.release / ".env").write_text("secret", encoding="utf-8")
        (self.release / "capture.jsonl").write_text("raw data", encoding="utf-8")
        (self.source / "private.py").write_text("private", encoding="utf-8")
        self.build()
        with zipfile.ZipFile(self.output) as archive:
            self.assertNotIn(".env", archive.namelist())
            self.assertNotIn("capture.jsonl", archive.namelist())
            self.assertNotIn("private.py", archive.namelist())

    def test_changed_wheel_same_size_refuses_publication(self):
        wheel = self.release / self.manifest["artifacts"][0]["file"]
        wheel.write_bytes(b"X" * wheel.stat().st_size)
        with self.assertRaisesRegex(ValueError, "changed since"):
            self.build()
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".analytics311-bundle-*")))

    def test_changed_handoff_same_size_refuses_publication(self):
        item = self.manifest["handoff_files"][0]
        (self.source / item["file"]).write_bytes(b"X" * item["bytes"])
        with self.assertRaisesRegex(ValueError, "changed since"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_missing_handoff_fails_closed(self):
        (self.source / self.manifest["handoff_files"][0]["file"]).unlink()
        with self.assertRaises(FileNotFoundError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_existing_archive_is_never_overwritten(self):
        self.output.write_bytes(b"previous archive")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.build()
        self.assertEqual(b"previous archive", self.output.read_bytes())

    def test_racing_archive_is_never_overwritten(self):
        link = package.os.link

        def race(source, target):
            target.write_bytes(b"racing archive")
            return link(source, target)

        with patch.object(package.os, "link", side_effect=race), self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(b"racing archive", self.output.read_bytes())
        self.assertFalse(list(self.root.glob(".analytics311-bundle-*")))

    def test_unverified_releases_cannot_be_transferred_as_verified(self):
        self.manifest["verification"]["status"] = "not_run"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "verified analytics311"):
            self.build()

    def test_malformed_or_ambiguous_verification_metadata_is_rejected(self):
        self.manifest["verification"] = "passed"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "verified analytics311"):
            self.build()
        path = self.release / "release-manifest.json"
        path.write_bytes(b'{"name":"analytics311","name":"other"}')
        with self.assertRaisesRegex(ValueError, "duplicate keys"):
            self.build()

    def test_extras_require_their_actual_smoke_evidence(self):
        self.manifest["extras_bundled"] = ["geo", "mcp"]
        self.manifest["install_requirement"] = "analytics311[geo,mcp]==0.4.0"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "not smoke-tested"):
            self.build()
        self.manifest["verification"].update(geo_tested=True, mcp_tested=True)
        self.save_manifest()
        self.build()

    def test_handoff_tools_require_clean_install_smoke_evidence(self):
        self.manifest["verification"].pop("handoff")
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "handoff smoke"):
            self.build()

    def test_export_stress_tool_requires_its_own_install_smoke(self):
        self.manifest["verification"]["handoff"].pop("export_stress")
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "export stress"):
            self.build()

    def test_manifest_cannot_include_other_source_files(self):
        self.manifest["handoff_files"][0]["file"] = "private.py"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "fixed allowlist"):
            self.build()

    def test_artifact_traversal_and_nonwheel_paths_are_rejected(self):
        original = self.manifest["artifacts"][1]["file"]
        for name in ("../private.whl", "/private.whl", "dependencies/../private.whl", "dependencies\\private.whl", "C:/private.whl", "private.txt"):
            self.manifest["artifacts"][1]["file"] = name
            self.save_manifest()
            with self.subTest(name=name), self.assertRaises((ValueError, FileNotFoundError)):
                self.build()
        self.manifest["artifacts"][1]["file"] = original

    def test_duplicate_paths_are_rejected(self):
        self.manifest["artifacts"].append(dict(self.manifest["artifacts"][1]))
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.build()

    def test_checksum_receipt_must_match_manifest(self):
        (self.release / "SHA256SUMS").write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "SHA256SUMS"):
            self.build()

    def test_input_byte_budget_is_enforced(self):
        with patch.object(package, "MAX_BUNDLE_BYTES", 100), self.assertRaisesRegex(ValueError, "budget"):
            self.build()

    def test_assembly_uses_streaming_reads(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")):
            self.build()

    def test_input_symlink_is_refused_without_needing_host_symlink_privileges(self):
        with patch.object(Path, "is_symlink", return_value=True), self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()

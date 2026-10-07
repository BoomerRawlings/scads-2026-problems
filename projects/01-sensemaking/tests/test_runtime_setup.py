"""Offline setup safety checks; no downloads, real cache edits, or execution."""

import hashlib
import copy
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup_local_runtime.py"
SPEC = importlib.util.spec_from_file_location("setup_local_runtime", SCRIPT)
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class RuntimeSetupTests(unittest.TestCase):
    def test_curated_cli_plans_match_pinned_assets_without_network_or_writes(self):
        cases = [(None, "baseline-2b", "runtime-manifest.json", "Qwen3-VL-2B-Instruct-Q4_K_M"),
                 ("baseline-2b", "baseline-2b", "runtime-manifest.json", "Qwen3-VL-2B-Instruct-Q4_K_M"),
                 ("candidate-4b", "candidate-4b", "runtime-candidate-qwen35.json", "Qwen3.5-4B-Q4_K_M"),
                 ("candidate-9b", "candidate-9b", "runtime-candidate-qwen35-9b.json", "Qwen3.5-9B-Q3_K_M"),
                 ("candidate-9b-vulkan", "candidate-9b-vulkan", "runtime-candidate-qwen35-9b-vulkan.json", "Qwen3.5-9B-Q3_K_M")]
        for option, profile, filename, alias in cases:
            with self.subTest(profile=option), tempfile.TemporaryDirectory() as directory:
                cache = Path(directory) / "untouched-cache"
                argv = [str(SCRIPT), "--cache-dir", str(cache)] + (["--profile", option] if option else [])
                stdout = io.StringIO()
                with patch.object(setup.sys, "argv", argv), redirect_stdout(stdout), patch.object(setup, "install") as install, patch.object(setup.urllib.request, "urlopen") as request:
                    self.assertEqual(setup.main(), 0)
                plan = json.loads(stdout.getvalue())
                manifest = json.loads((SCRIPT.parents[1] / "docs" / filename).read_text(encoding="utf-8"))
                self.assertEqual(plan["profile"], profile)
                self.assertEqual(plan["manifest"], "docs/" + filename)
                self.assertEqual(plan["model_alias"], alias)
                self.assertEqual(plan["download_bytes"], manifest["total_download_bytes"])
                self.assertEqual(plan["runtime_directory"], str(setup.runtime_directory(cache, manifest)))
                self.assertEqual(plan["assets"], [{k: asset[k] for k in ("filename", "size_bytes", "sha256")} for asset in manifest["assets"]])
                install.assert_not_called()
                request.assert_not_called()
                self.assertFalse(cache.exists())

    def test_9b_pinned_assets_totals_and_cache_isolation(self):
        manifest = json.loads((SCRIPT.parents[1] / "docs/runtime-candidate-qwen35-9b.json").read_text())
        previous = json.loads((SCRIPT.parents[1] / "docs/runtime-candidate-qwen35.json").read_text())
        revision = "3885219b6810b007914f3a7950a8d1b469d598a5"
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["platform"], "windows-arm64-cpu")
        self.assertEqual(manifest["model"]["revision"], revision)
        self.assertEqual(manifest["model"]["license"], "Apache-2.0")
        assets = {asset["role"]: asset for asset in manifest["assets"]}
        old_assets = {asset["role"]: asset for asset in previous["assets"]}
        self.assertEqual(set(assets), {"runtime_archive", "language_model", "vision_projector"})
        self.assertEqual(assets["runtime_archive"], old_assets["runtime_archive"])
        expected = {
            "language_model": ("Qwen3.5-9B-Q3_K_M.gguf", 4673643744, "8fed90306e4f019e2bf35f3766470b7bc59ea1a9dae00f5ceb20b43cb5514393"),
            "vision_projector": ("mmproj-F16.gguf", 918166080, "f70dc3509053962b0d0d3ee8a7eacebf5d60aa560cad78254ae8698516ae029f"),
        }
        for role, (filename, size, checksum) in expected.items():
            with self.subTest(role=role):
                self.assertEqual((assets[role]["filename"], assets[role]["size_bytes"], assets[role]["sha256"]), (filename, size, checksum))
                self.assertEqual(assets[role]["url"], f"https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/{revision}/{filename}")
                self.assertNotEqual(setup.asset_path(Path("cache"), manifest, assets[role]), setup.asset_path(Path("cache"), previous, old_assets[role]))
        self.assertEqual(manifest["total_download_bytes"], sum(asset["size_bytes"] for asset in assets.values()))
        self.assertEqual(manifest["total_download_bytes"], 5604074472)

    def test_unknown_profile_rejected_before_install_or_network(self):
        for value in ("unknown", "https://example.invalid/manifest.json", "../manifest.json"):
            with self.subTest(profile=value), patch.object(setup.sys, "argv", [str(SCRIPT), "--profile", value, "--download"]), redirect_stderr(io.StringIO()), patch.object(setup, "install") as install, patch.object(setup.urllib.request, "urlopen") as request:
                with self.assertRaises(SystemExit) as error:
                    setup.main()
                self.assertEqual(error.exception.code, 2)
                install.assert_not_called()
                request.assert_not_called()

    def test_vulkan_manifest_pin_model_reuse_and_sibling_runtime_directory(self):
        root = SCRIPT.parents[1] / "docs"
        cpu = json.loads((root / "runtime-candidate-qwen35-9b.json").read_text())
        vulkan = json.loads((root / "runtime-candidate-qwen35-9b-vulkan.json").read_text())
        self.assertEqual(vulkan["platform"], "windows-arm64-vulkan")
        self.assertNotIn("verified_version_output", vulkan["runtime"])
        self.assertEqual(vulkan["model"], cpu["model"])
        self.assertEqual(vulkan["assets"][1:], cpu["assets"][1:])
        runtime = vulkan["assets"][0]
        self.assertEqual(runtime["filename"], "llama-b11457-bin-win-vulkan-arm64.zip")
        self.assertEqual(runtime["size_bytes"], 25918589)
        self.assertEqual(runtime["sha256"], "189d661d7a83b9a50fb10a6b701bb7b6d8beeb4c3efd0f108224590e4476029d")
        self.assertEqual(runtime["url"], "https://github.com/ggml-org/llama.cpp/releases/download/b11457/" + runtime["filename"])
        self.assertEqual(vulkan["total_download_bytes"], 5617728413)
        self.assertEqual(vulkan["total_download_bytes"], sum(a["size_bytes"] for a in vulkan["assets"]))
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            cpu_dir = setup.runtime_directory(cache, cpu)
            gpu_dir = setup.runtime_directory(cache, vulkan)
            self.assertEqual(cpu_dir, cache / "llama.cpp/b11457")
            self.assertEqual(gpu_dir, cache / "llama.cpp/b11457-vulkan-arm64")
            self.assertFalse(gpu_dir.is_relative_to(cpu_dir))
            for asset in vulkan["assets"][1:]:
                self.assertEqual(setup.asset_path(cache, vulkan, asset), setup.asset_path(cache, cpu, asset))
            self.assertNotEqual(setup.asset_path(cache, vulkan, runtime), setup.asset_path(cache, cpu, cpu["assets"][0]))

    def test_vulkan_inert_install_preserves_existing_cpu_cache(self):
        manifest = json.loads((SCRIPT.parents[1] / "docs/runtime-candidate-qwen35-9b-vulkan.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            cpu = cache / "llama.cpp/b11457/bin"
            cpu.mkdir(parents=True)
            (cpu / "llama-server.exe").write_bytes(b"existing CPU server")
            (cpu / "ggml-cpu.dll").write_bytes(b"existing CPU backend")
            originals = {p.name: p.read_bytes() for p in cpu.iterdir()}
            archive = Path(temporary) / manifest["assets"][0]["filename"]
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("bin/llama-server.exe", b"inert Vulkan test server")
                stream.writestr("bin/ggml-vulkan.dll", b"inert Vulkan test backend")
            paths = {"runtime_archive": archive, "language_model": Path(temporary) / "model.gguf", "vision_projector": Path(temporary) / "projector.gguf"}
            with patch.object(setup, "require_supported_platform"), patch.object(setup.shutil, "disk_usage", return_value=SimpleNamespace(free=10**12)), patch.object(setup, "download_asset", side_effect=lambda cache, manifest, asset: paths[asset["role"]]), patch.object(setup.urllib.request, "urlopen") as request:
                result = setup.install(cache, manifest)
                request.assert_not_called()
            self.assertEqual({p.name: p.read_bytes() for p in cpu.iterdir()}, originals)
            self.assertEqual(len(list(cpu.parent.rglob("llama-server.exe"))), 1)
            self.assertEqual(Path(result["server"]), cache / "llama.cpp/b11457-vulkan-arm64/bin/llama-server.exe")
            self.assertEqual(Path(result["server"]).read_bytes(), b"inert Vulkan test server")

    def test_backend_mismatch_or_path_values_refused_before_downloads_or_writes(self):
        original = json.loads((SCRIPT.parents[1] / "docs/runtime-candidate-qwen35-9b-vulkan.json").read_text())
        changes = [lambda m: m.update(platform="../b11457"), lambda m: m["runtime"].update(version="../b11457"),
                   lambda m: m["assets"][0].update(filename="llama-b11457-bin-win-cpu-arm64.zip"),
                   lambda m: m.update(assets=m["assets"] + [m["assets"][0]])]
        for change in changes:
            manifest = copy.deepcopy(original)
            change(manifest)
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                cache = Path(temporary) / "untouched"
                with patch.object(setup, "require_supported_platform"), patch.object(setup, "download_asset") as download:
                    with self.assertRaisesRegex(ValueError, "curated backend"):
                        setup.install(cache, manifest)
                    download.assert_not_called()
                self.assertFalse(cache.exists())

    def test_linked_variant_destination_refused_before_cache_install(self):
        manifest = json.loads((SCRIPT.parents[1] / "docs/runtime-candidate-qwen35-9b-vulkan.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache"
            target = cache / "llama.cpp/b11457-vulkan-arm64"
            with patch.object(setup.Path, "is_symlink", autospec=True, side_effect=lambda path: path == target), patch.object(setup, "require_supported_platform"), patch.object(setup, "download_asset") as download:
                with self.assertRaisesRegex(ValueError, "Linked runtime"):
                    setup.install(cache, manifest)
                download.assert_not_called()
            self.assertFalse(cache.exists())

    def test_hard_linked_runtime_file_cannot_overwrite_cpu_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "cpu-server.exe"
            original.write_bytes(b"original CPU")
            destination = root / "vulkan"
            destination.mkdir()
            (destination / "llama-server.exe").hardlink_to(original)
            archive = root / "runtime.zip"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("new-file.dll", b"not extracted on refusal")
                stream.writestr("llama-server.exe", b"replacement")
            with self.assertRaisesRegex(ValueError, "Hard-linked"):
                setup.extract_archive(archive, destination)
            self.assertEqual(original.read_bytes(), b"original CPU")
            self.assertFalse((destination / "new-file.dll").exists())

    def test_unsupported_platform_stops_before_cache_or_network(self):
        for system, machine in (("Linux", "aarch64"), ("Darwin", "arm64"), ("Windows", "AMD64"), ("Windows", "x86")):
            with self.subTest(system=system, machine=machine), tempfile.TemporaryDirectory() as directory:
                cache = Path(directory) / "untouched-cache"
                with patch.object(setup.platform, "system", return_value=system), patch.object(setup.platform, "machine", return_value=machine), patch.object(setup.urllib.request, "urlopen") as request:
                    with self.assertRaisesRegex(ValueError, "Windows ARM64 only"):
                        setup.install(cache, {})
                    request.assert_not_called()
                    self.assertFalse(cache.exists())

    def test_windows_arm64_aliases_supported(self):
        for machine in ("ARM64", "arm64", "aarch64"):
            with self.subTest(machine=machine), patch.object(setup.platform, "system", return_value="Windows"), patch.object(setup.platform, "machine", return_value=machine):
                setup.require_supported_platform()

    def test_corruption_rejected_even_when_size_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asset.bin"
            original = b"verified model bytes"
            asset = {"filename": path.name, "size_bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
            path.write_bytes(original)
            setup.verify(path, asset)
            path.write_bytes(b"X" + original[1:])
            with self.assertRaisesRegex(ValueError, "SHA256"):
                setup.verify(path, asset)
            path.write_bytes(original[:-1])
            with self.assertRaisesRegex(ValueError, "Size"):
                setup.verify(path, asset)

    def test_archive_escape_rejected_before_extracting_any_member(self):
        for unsafe in ("../escape.txt", "..\\escape.txt", "/escape.txt", "C:/escape.txt"):
            with self.subTest(member=unsafe), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive_path, destination = root / "runtime.zip", root / "runtime"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("llama-server.exe", b"inert test bytes")
                    archive.writestr(unsafe, b"must not extract")
                with self.assertRaisesRegex(ValueError, "escapes"):
                    setup.extract_archive(archive_path, destination)
                self.assertFalse(destination.exists())
                self.assertFalse((root / "escape.txt").exists())

    def test_archive_with_local_paths_extracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path, destination = root / "runtime.zip", root / "runtime"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("bin/llama-server.exe", b"inert test bytes")
            setup.extract_archive(archive_path, destination)
            self.assertEqual((destination / "bin" / "llama-server.exe").read_bytes(), b"inert test bytes")


if __name__ == "__main__":
    unittest.main()

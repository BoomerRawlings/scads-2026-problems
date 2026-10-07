"""Download pinned, verified llama.cpp + Qwen VL assets into a dedicated cache.

Installer support: Windows ARM64 only; other platforms fail before downloads.
Default is a read-only plan. --profile selects one of the curated pinned asset sets.
This script never launches a model server or changes global configuration.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PureWindowsPath
import platform
import shutil
import sys
import urllib.request
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT / "docs" / "runtime-manifest.json"
PROFILES = {
    "baseline-2b": ("docs/runtime-manifest.json", "Qwen3-VL-2B-Instruct-Q4_K_M"),
    "candidate-4b": ("docs/runtime-candidate-qwen35.json", "Qwen3.5-4B-Q4_K_M"),
    "candidate-9b": ("docs/runtime-candidate-qwen35-9b.json", "Qwen3.5-9B-Q3_K_M"),
    "candidate-9b-vulkan": ("docs/runtime-candidate-qwen35-9b-vulkan.json", "Qwen3.5-9B-Q3_K_M"),
}
# Fixed sibling directories: never place a backend below the CPU directory,
# where recursive llama-server discovery would also pick up the new binary.
RUNTIME_LAYOUTS = {
    ("b11457", "windows-arm64-cpu"): ("llama-b11457-bin-win-cpu-arm64.zip", "b11457"),
    ("b11457", "windows-arm64-vulkan"): ("llama-b11457-bin-win-vulkan-arm64.zip", "b11457-vulkan-arm64"),
}
DEFAULT_CACHE = Path.home() / ".cache" / "scads-sensemaking"


def require_supported_platform() -> None:
    system, machine = platform.system(), platform.machine()
    if system != "Windows" or machine.casefold() not in {"arm64", "aarch64"}:
        raise ValueError(f"Installer supports Windows ARM64 only; detected {system} {machine}. No downloads started.")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path: Path, asset: dict) -> None:
    if path.stat().st_size != asset["size_bytes"]:
        raise ValueError(f"Size verification failed: {asset['filename']}")
    if sha256(path) != asset["sha256"]:
        raise ValueError(f"SHA256 verification failed: {asset['filename']}")


def asset_path(cache: Path, manifest: dict, asset: dict) -> Path:
    if asset["role"] == "runtime_archive":
        return cache / "downloads" / asset["filename"]
    return cache / "models" / manifest["model"]["revision"] / asset["filename"]


def download_asset(cache: Path, manifest: dict, asset: dict) -> Path:
    destination = asset_path(cache, manifest, asset)
    if destination.exists():
        verify(destination, asset)
        print(f"Verified cached {asset['filename']}", file=sys.stderr, flush=True)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "scads-sensemaking-runtime-setup/1"})
    print(f"Downloading {asset['filename']} ({asset['size_bytes']} bytes)", file=sys.stderr, flush=True)
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as stream:
        received = 0
        while block := response.read(1024 * 1024):
            received += len(block)
            if received > asset["size_bytes"]:
                raise ValueError(f"Download exceeded pinned size: {asset['filename']}")
            stream.write(block)
    verify(partial, asset)
    partial.replace(destination)
    print(f"Verified downloaded {asset['filename']}", file=sys.stderr, flush=True)
    return destination


def reject_linked_components(path: Path) -> Path:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        try:
            reparse_tag = getattr(current.lstat(), "st_reparse_tag", None)
        except FileNotFoundError:
            reparse_tag = None
        if current.is_symlink() or reparse_tag == 0xA0000003:
            raise ValueError("Linked runtime destination rejected")
    return absolute


def runtime_directory(cache: Path, manifest: dict) -> Path:
    layout = RUNTIME_LAYOUTS.get((manifest.get("runtime", {}).get("version"), manifest.get("platform")))
    archives = [asset for asset in manifest.get("assets", []) if asset.get("role") == "runtime_archive"]
    if layout is None or len(archives) != 1 or archives[0].get("filename") != layout[0]:
        raise ValueError("Runtime platform, version and archive must match a curated backend")
    return reject_linked_components(cache / "llama.cpp" / layout[1])


def extract_archive(archive_path: Path, runtime_dir: Path) -> None:
    runtime_dir = reject_linked_components(runtime_dir)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_path = member.filename.replace("\\", "/")
            target = runtime_dir / member_path
            if PureWindowsPath(member_path).drive or not target.resolve().is_relative_to(runtime_dir.resolve()):
                raise ValueError("Archive member escapes the dedicated runtime directory")
            reject_linked_components(target)
            if target.is_file() and target.stat().st_nlink > 1:
                raise ValueError("Hard-linked runtime destination rejected")
        archive.extractall(runtime_dir)


def install(cache: Path, manifest: dict) -> dict:
    require_supported_platform()
    runtime_dir = runtime_directory(cache, manifest)
    cache.mkdir(parents=True, exist_ok=True)
    missing_bytes = sum(asset["size_bytes"] for asset in manifest["assets"] if not asset_path(cache, manifest, asset).exists())
    if shutil.disk_usage(cache).free < missing_bytes + 512 * 1024 * 1024:
        raise ValueError("Insufficient free disk for missing assets and extraction headroom")
    with ThreadPoolExecutor(max_workers=3) as pool:
        # Every result is awaited; a failed hash prevents archive extraction.
        downloaded = list(pool.map(lambda asset: download_asset(cache, manifest, asset), manifest["assets"]))
    paths = {asset["role"]: path for asset, path in zip(manifest["assets"], downloaded)}
    runtime_dir.mkdir(parents=True, exist_ok=True)
    extract_archive(paths["runtime_archive"], runtime_dir)
    servers = list(runtime_dir.rglob("llama-server.exe"))
    if len(servers) != 1:
        raise ValueError("Verified runtime archive did not contain one llama-server.exe")
    return {
        "verified": True,
        "runtime_version": manifest["runtime"]["version"],
        "model_revision": manifest["model"]["revision"],
        "server": str(servers[0]),
        "model": str(paths["language_model"]),
        "mmproj": str(paths["vision_projector"]),
        "note": "No server launched. Paths are local installation output; do not commit them.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="baseline-2b",
                        help="Curated pinned asset profile; candidate profiles do not establish resource fit or analytic acceptance")
    parser.add_argument("--download", action="store_true", help="Download and verify the pinned public assets")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    manifest_file, model_alias = PROFILES[args.profile]
    manifest = json.loads((PROJECT / manifest_file).read_text(encoding="utf-8"))
    selection = {"profile": args.profile, "manifest": manifest_file, "model_alias": model_alias}
    cache = args.cache_dir.expanduser().resolve()
    if cache.is_relative_to(PROJECT.parent.parent):
        parser.error("Use an external cache directory; do not place model files in the project")
    if not args.download:
        print(json.dumps({**selection, "download_bytes": manifest["total_download_bytes"], "cache": str(cache), "runtime_directory": str(runtime_directory(cache, manifest)), "assets": [{k: a[k] for k in ("filename", "size_bytes", "sha256")} for a in manifest["assets"]], "next": f"Run again with --profile {args.profile} --download to install; no files changed."}, indent=2))
        return 0
    try:
        result = install(cache, manifest)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Runtime setup failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({**selection, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

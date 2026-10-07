"""Assemble a Windows offline runtime from qualified wheels and the local CPython base.

No downloads or global installation. This complements wheelhouse proof with
relocation proof; it does not claim a clean OS or native-network isolation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from package_offline import _SMOKE, sha256, write_json

PROJECT = Path(__file__).resolve().parents[1]


def run(command, cwd):
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
    result = subprocess.run([str(part) for part in command], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:] + result.stdout[-2000:])
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("discovery", "extraction"), default="discovery")
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        raise ValueError("This assembler is qualified only for the current Windows runtime layout")
    source = Path(sys.base_prefix).resolve()
    if not (source / "python.exe").is_file() or not (source / "LICENSE.txt").is_file():
        raise ValueError("Expected a complete local Windows CPython base with license")
    wheelhouse, output = args.wheelhouse.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Use a new output directory; existing artifacts are never overwritten")
    lock = wheelhouse / f"requirements-{args.profile}.lock"
    if not lock.is_file():
        raise ValueError("Matching qualified wheelhouse lock missing")
    output.mkdir(parents=True)
    runtime = output / "runtime"
    shutil.copytree(source, runtime, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    python = runtime / "python.exe"
    # Bundled pip is run from the relocated interpreter; external Python/uv are unnecessary.
    run([python, "-I", "-m", "pip", "--isolated", "install", "--disable-pip-version-check", "--no-index",
         "--no-cache-dir", "--require-hashes", "--target", runtime / "Lib" / "site-packages",
         "--find-links", wheelhouse / "wheels", "-r", lock], output)
    (output / "vopt.cmd").write_text('@echo off\r\n"%~dp0runtime\\python.exe" -I -m vopt %*\r\n', encoding="utf-8")
    shutil.copy2(lock, output / lock.name)
    shutil.copy2(wheelhouse / "manifest.json", output / "wheelhouse-manifest.json")
    shutil.copytree(wheelhouse / "licenses", output / "licenses")
    # Reproducible source allowlist: never package extraction workspaces, global state or credentials.
    source_files = []
    folders = ("vopt", "schemas") if args.profile == "discovery" else ("vopt", "scripts", "tests", "docs", "eval", "schemas")
    for folder in folders:
        base = PROJECT / folder
        if base.exists():
            source_files.extend(path for path in base.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".html", ".css", ".js", ".md", ".json"})
    root_names = ("pyproject.toml",) if args.profile == "discovery" else ("pyproject.toml", "README.md", "ACCEPTANCE.md", "ROADMAP.md", "CORPUS.md", "RUNBOOK.md")
    source_files.extend(PROJECT / name for name in root_names if (PROJECT / name).is_file())
    with zipfile.ZipFile(output / "project-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(source_files)):
            archive.write(path, path.relative_to(PROJECT).as_posix())
    # Research references, original PDFs, OCR and review ledgers belong in a separate explicit artifact.
    with zipfile.ZipFile(output / "project-source.zip") as archive:
        if any(name.startswith(("data/", "runs/", "examples/")) for name in archive.namelist()):
            raise ValueError("Private research data must not enter a runtime package")
    proofdir = output / "verification"
    proofdir.mkdir()
    (proofdir / "smoke.py").write_text(_SMOKE, encoding="utf-8")
    started = time.perf_counter()
    evidence = json.loads(run([python, "-I", proofdir / "smoke.py", args.profile], proofdir))
    evidence.update(packaged_python_runtime=True, external_python_required=False, external_installer_required=False,
        runtime_relocated=True, elapsed_seconds=round(time.perf_counter()-started, 3),
        limits="Existing Windows host; Python socket guard only. Full source/license redistribution qualification remains separate.")
    write_json(output / "proof-portable.json", evidence)
    (output / "START.txt").write_text(
        "VOPT offline portable runtime\n\nRun vopt.cmd doctor from this folder.\n"
        "Import: vopt.cmd import released.json --catalog catalog.sqlite3\n"
        "Search: vopt.cmd search \"manuals with horsepower\" --catalog catalog.sqlite3\n"
        "Interface: vopt.cmd serve --catalog catalog.sqlite3 --port 0 (open the printed local URL)\n"
        "Extraction profile only: vopt.cmd ingest manifest.jsonl --workspace private\n"
        "Review: vopt.cmd serve --workspace private --port 8763\n\n"
        "No originals, approved corpus, or human validation are included. project-source.zip contains the runtime source.\n"
        "Python and dependencies are included with notices. This is a local qualification artifact;\n"
        "PyMuPDF's AGPL/commercial terms and corresponding-source requirements must be resolved for redistribution.\n", encoding="utf-8")
    files = [{"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(output.rglob("*")) if path.is_file() and "__pycache__" not in path.parts]
    write_json(output / "portable-manifest.json", {"schema_version": 1, "profile": args.profile,
        "python": platform.python_version(), "interpreter_machine": platform.machine(), "files": files,
        "proof": "proof-portable.json", "network_downloads": 0})
    if args.zip:
        archive_path = output.parent / (output.name + ".zip")
        if archive_path.exists():
            raise ValueError("Archive path already exists")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(output).as_posix())
    print(json.dumps({"status": "passed", "profile": args.profile, "output": str(output),
        "files": len(files), "bytes": sum(item["bytes"] for item in files), "python_network_attempts": evidence["python_network_attempts"]}, indent=2))


if __name__ == "__main__":
    main()

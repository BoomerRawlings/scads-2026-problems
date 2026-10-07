"""Build wheel+sdist, audit packaged assets, and write artifact SHA-256 hashes.

Run with an interpreter having the build frontend installed. Build tooling is
separate from the application's dependency-free runtime.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tomllib
import zipfile


PROJECT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def expected_assets(project=PROJECT):
    """Inventory only the declared public demo, schemas, and static assets."""
    mappings = (("fixtures/pump", {".json", ".jsonl", ".md"}), ("schemas", {".json"}), ("static", None))
    result = {}
    for relative, suffixes in mappings:
        directory = project / relative
        if not directory.is_dir():
            raise RuntimeError(f"Missing required resource directory: {relative}")
        paths = sorted(path for path in directory.rglob("*") if path.is_file())
        for path in paths:
            if any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(directory).parts):
                continue
            if suffixes is not None and path.suffix not in suffixes:
                continue
            result[path.relative_to(project).as_posix()] = path.read_bytes()
    for required in ("fixtures/pump/manifest.json", "fixtures/pump/gold.json", "schemas/record.schema.json", "schemas/assertion.schema.json", "static/index.html"):
        if required not in result:
            raise RuntimeError(f"Missing required resource file: {required}")
    return result


def audit_artifacts(wheel, sdist, assets):
    """The wheel and source archive must preserve the exact declared bytes."""
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for relative, content in assets.items():
            packaged = "graphrag_discovery/" + relative
            if packaged not in names or archive.read(packaged) != content:
                raise RuntimeError(f"Wheel resource missing or changed: {packaged}")
        if "graphrag_discovery/resources.py" not in names:
            raise RuntimeError("Wheel lacks resource access implementation")
        if any(name.endswith(('.sqlite3', '.pyc')) or '/__pycache__/' in name for name in names):
            raise RuntimeError("Wheel contains runtime or cache output")
    with tarfile.open(sdist, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers()}
        roots = {name.split("/", 1)[0] for name in members}
        if len(roots) != 1:
            raise RuntimeError("Source archive must contain one project root")
        root = next(iter(roots))
        for relative, content in assets.items():
            stream = archive.extractfile(root + "/" + relative)
            if stream is None or stream.read() != content:
                raise RuntimeError(f"Source resource missing or changed: {relative}")
        for relative in ("pyproject.toml", "scripts/build_distribution.py", "scripts/smoke_install.py", "docs/installation.md"):
            if root + "/" + relative not in members:
                raise RuntimeError(f"Source distribution missing: {relative}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=PROJECT / "dist")
    parser.add_argument("--no-isolation", action="store_true", help="Use already-installed setuptools/build tooling")
    args = parser.parse_args(argv)
    config = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    normalized = config["name"].replace("-", "_")
    output = args.outdir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assets = expected_assets()
    command = [sys.executable, "-m", "build", "--outdir", str(output)]
    if args.no_isolation:
        command.append("--no-isolation")
    # Default build behavior builds the wheel FROM the sdist, checking that the
    # sdist is independently complete rather than relying on checkout-only files.
    subprocess.run(command, cwd=PROJECT, check=True)
    wheel = output / f"{normalized}-{config['version']}-py3-none-any.whl"
    sdist = output / f"{normalized}-{config['version']}.tar.gz"
    audit_artifacts(wheel, sdist, assets)
    report = {
        "schema_version": "1", "distribution": config["name"], "version": config["version"],
        "created_at": datetime.now(timezone.utc).isoformat(), "python": sys.version.split()[0],
        "platform": sys.platform, "build_frontend": metadata.version("build"),
        "build_mode": "wheel-from-sdist", "runtime_dependencies": config.get("dependencies", []),
        "artifacts": [{"path": path.name, "sha256": sha256(path.read_bytes()), "bytes": path.stat().st_size} for path in (wheel, sdist)],
        "resources": [{"path": path, "sha256": sha256(content), "bytes": len(content)} for path, content in sorted(assets.items())],
    }
    manifest = output / "artifacts.json"
    manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": True, "manifest": str(manifest), "resources_verified": len(assets)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

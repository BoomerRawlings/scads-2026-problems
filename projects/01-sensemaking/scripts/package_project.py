"""Build or verify a deterministic, allowlisted source ZIP. No downloads or model execution."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
PREFIX = "scads-sensemaking/"
OWNER = "scads-sensemaking-source-v1"
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_PACKAGE_BYTES + 2 * 1024 * 1024
ROOT_FILES = (".gitignore", "README.md", "requirements.txt", "report.schema.json", "sensemaking.py",
              "mcp_server.py", "media_tools.py", "run_agent.py", "local_agent.py", "evidence_catalog.py", "local_context.py")
RECORD_FILES = ("report.json", "report.md", "run-metadata.json", "tool-trace.json", "evidence-ledger.json",
                "REVIEW.md", "failure.json")
PATTERNS = ("docs/*.md", "docs/*.json", "tests/test_*.py", "scripts/*.py", "data/*.json", "data/*.csv", "data/*.md",
            "data/documents/*.txt", "data/annotations/*.txt", "data/transcripts/*.txt", "data/media/*.png", "data/media/*.mp4",
            "evaluations/local-pilot/runtime-profile-*.json", "evaluations/local-pilot/*probe*.json",
            "evaluations/public-pilot/runtime-profile-*.json", "evaluations/public-pilot/*probe*.json",
            "evaluations/public-pilot/*probe*.review.md")
SNAPSHOT_FILES = set(ROOT_FILES) | {"snapshot.json", "runtime-manifest.json", "runtime-candidate-qwen35.json",
                                    "runtime-candidate-qwen35-9b.json", "import_public_statements.py",
                                    "import_public_data.py", "capture_public_data.py"}
RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def relative_path(value):
    if not isinstance(value, str):
        raise ValueError("Unsafe package-relative path")
    path = PurePosixPath(value)
    if (not value or "\\" in value or ":" in value
            or path.is_absolute() or any(part in {"", ".", ".."} or part.endswith((".", " "))
                                        or part.split(".")[0].lower() in RESERVED_NAMES for part in value.split("/"))):
        raise ValueError("Unsafe package-relative path")
    return path


def linked(path):
    if path.is_symlink():
        return True
    try:
        return getattr(path.lstat(), "st_reparse_tag", None) == 0xA0000003  # Windows junction, including Python 3.11.
    except FileNotFoundError:
        return False


def read_source(project, relative):
    parts = relative_path(relative).parts
    path = project
    for part in parts:
        path = path / part
        if linked(path):
            raise ValueError("Linked source rejected: " + relative)
    if not path.resolve().is_relative_to(project.resolve()) or not path.is_file():
        raise ValueError("Missing or escaping source: " + relative)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Source file exceeds byte limit: " + relative)
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Source file grew beyond byte limit: " + relative)
    return raw


def collect_files(project=PROJECT, include_showcase=False):
    project = Path(project).resolve()
    paths = set(ROOT_FILES) | {"evaluations/local-pilot/REVIEW-PROTOCOL.md", "evaluations/local-pilot/probe_vision.py",
                               "evaluations/public-pilot/PROTOCOL.md"}
    paths.update("showcase/" + name for name in ("index.html", "styles.css", "app.js", "cases.json", "README.md", "QA.md", "test_showcase.py"))
    for pattern in PATTERNS:
        paths.update(p.relative_to(project).as_posix() for p in project.glob(pattern))
    for parent in ("examples/*", "evaluations/local-pilot/local-*", "evaluations/public-pilot/public-*"):
        for name in (*RECORD_FILES, "rejected-report-[0-9][0-9].json", "media-observation-[0-9][0-9].json"):
            paths.update(p.relative_to(project).as_posix() for p in project.glob(parent + "/" + name))
    snapshots = [path for group in ("local-pilot", "public-pilot")
                 for path in project.glob(f"evaluations/{group}/implementation-v*/snapshot.json")]
    for snapshot in snapshots:
        base = snapshot.parent.relative_to(project).as_posix()
        data = json.loads(read_source(project, base + "/snapshot.json"))
        for name, expected in data["files"].items():
            if name not in SNAPSHOT_FILES:
                raise ValueError("Snapshot entry outside source allowlist")
            relative = base + "/" + name
            if digest(read_source(project, relative)) != expected:
                raise ValueError("Historical source snapshot hash mismatch: " + relative)
            paths.add(relative)
        paths.add(base + "/snapshot.json")
        paths.update(base + "/" + name for name in SNAPSHOT_FILES if (snapshot.parent / name).is_file())
    files = {path: read_source(project, path) for path in sorted(paths)}

    # Existing importer verifies fixed source URLs, revisions, lengths and SHA256 offline.
    import import_public_data as importer
    import capture_public_data as capture
    public = "datasets/public-research/"
    sources, capture_bytes = importer.load_sources(project / public)
    expected_files, totals = importer.build_dataset(sources, capture_bytes)
    files[public + "capture-manifest.json"] = capture_bytes
    for source in sources:
        relative = public + capture.raw_path(source["spec"])
        if read_source(project, relative) != source["raw"]:
            raise ValueError("Public source changed while packaging")
        files[relative] = source["raw"]
    for name, expected in expected_files.items():
        relative = public + "imported/" + name
        raw = read_source(project, relative)
        if raw != expected:
            raise ValueError("Public import differs from verified offline reproduction: " + relative)
        files[relative] = raw

    if include_showcase:
        import build_showcase
        expected_showcase = build_showcase.package_files(project)
        manifest_path = "showcase/dist/package-manifest.json"
        raw_manifest = read_source(project, manifest_path)
        manifest = json.loads(raw_manifest)
        if manifest.get("owner") != build_showcase.OWNER:
            raise ValueError("Unrecognized showcase build")
        actual = {entry["path"]: (entry["sha256"], entry["size_bytes"]) for entry in manifest["files"]}
        expected = {path: (digest(raw), len(raw)) for path, raw in expected_showcase.items()}
        if actual != expected or len(actual) != len(manifest["files"]):
            raise ValueError("Showcase build stale or inconsistent; rebuild after sources are frozen")
        for name, expected in expected_showcase.items():
            relative = "showcase/dist/" + name
            raw = read_source(project, relative)
            if raw != expected:
                raise ValueError("Showcase file changed: " + relative)
            files[relative] = raw
        files[manifest_path] = raw_manifest
    if sum(map(len, files.values())) > MAX_PACKAGE_BYTES:
        raise ValueError("Package content exceeds byte limit")
    # Catch concurrent source edits; every member is included as original bytes.
    if any(read_source(project, path) != raw for path, raw in files.items()):
        raise ValueError("Source changed while packaging; retry after the source freeze")
    return files, {"public_import": totals, "historical_snapshots": len(snapshots), "showcase_included": include_showcase}


def archive_bytes(files, verification):
    manifest = {"owner": OWNER, "format": "ZIP_STORED; sorted names; 1980-01-01 UTC; regular files mode 0644",
                "root": PREFIX, "verification": verification,
                "excludes": [".venv", "runs", "raw logs", "machine caches", "model weights", "symlinks/junctions",
                             "global state", ".codex", "unlisted files"],
                "content_bytes": sum(map(len, files.values())),
                "files": [{"path": path, "sha256": digest(raw), "size_bytes": len(raw)} for path, raw in sorted(files.items())]}
    manifest_raw = encoded(manifest)
    members = {**files, "PACKAGE-MANIFEST.json": manifest_raw}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(members.items()):
            info = zipfile.ZipInfo(PREFIX + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw)
    return output.getvalue(), manifest_raw


def read_archive(path):
    with path.open("rb") as stream:
        raw = stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds byte limit")
    return raw


def verify_archive(raw, evaluate=False):
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds byte limit")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)) or names != sorted(names):
            raise ValueError("Duplicate or unsorted archive members")
        if sum(entry.file_size for entry in entries) > MAX_PACKAGE_BYTES + 1024 * 1024:
            raise ValueError("Expanded archive exceeds byte limit")
        for entry in entries:
            relative_path(entry.filename)
            if (not entry.filename.startswith(PREFIX) or entry.is_dir() or entry.file_size > MAX_FILE_BYTES
                    or stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG
                    or entry.compress_type != zipfile.ZIP_STORED or entry.date_time != (1980, 1, 1, 0, 0, 0)):
                raise ValueError("Unsafe or noncanonical archive member")
        manifest = json.loads(archive.read(PREFIX + "PACKAGE-MANIFEST.json"))
        if manifest.get("owner") != OWNER or manifest.get("root") != PREFIX:
            raise ValueError("Unrecognized source manifest")
        records = manifest["files"]
        expected = {PREFIX + entry["path"] for entry in records} | {PREFIX + "PACKAGE-MANIFEST.json"}
        if len(records) + 1 != len(names) or set(names) != expected:
            raise ValueError("Archive differs from manifest inventory")
        for entry in records:
            relative_path(entry["path"])
            content = archive.read(PREFIX + entry["path"])
            if len(content) != entry["size_bytes"] or digest(content) != entry["sha256"]:
                raise ValueError("Archive member hash or size mismatch: " + entry["path"])
        if sum(entry["size_bytes"] for entry in records) != manifest["content_bytes"]:
            raise ValueError("Manifest total mismatch")
        result = {"zip_sha256": digest(raw), "zip_bytes": len(raw), "source_files": len(records),
                  "zip_members": len(names), "content_bytes": manifest["content_bytes"], "hashes_verified": True}
        # Extract only validated regular files into a new temporary directory.
        with tempfile.TemporaryDirectory(prefix="scads-source-check-") as temporary:
            extracted = Path(temporary).resolve()
            for name in names:
                destination = extracted / name
                if not destination.resolve().is_relative_to(extracted):
                    raise ValueError("Extraction escaped temporary directory")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as stream:
                    stream.write(archive.read(name))
            for entry in records:
                if digest((extracted / PREFIX / entry["path"]).read_bytes()) != entry["sha256"]:
                    raise ValueError("Extracted member hash mismatch")
            result["extraction_verified"] = True
            if evaluate:
                completed = subprocess.run([sys.executable, "sensemaking.py", "evaluate"], cwd=extracted / PREFIX,
                                           capture_output=True, text=True, timeout=60, check=False)
                if completed.returncode:
                    raise ValueError("Extracted core regression failed; package not qualified")
                regression = json.loads(completed.stdout)
                if not regression.get("total") or regression.get("passed") != regression["total"]:
                    raise ValueError("Extracted core regression did not pass every case")
                result["core_regression"] = {"passed": regression["passed"], "total": regression["total"],
                                             "scope": "Authored retrieval regression; existing Python environment, no model install or inference"}
        return result


def build(name, include_showcase=False, project=PROJECT):
    if (not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", name) or name.endswith(".")
            or name.split(".")[0] in RESERVED_NAMES):
        raise ValueError("Use a portable lowercase package name, at most 80 characters")
    output = Path(project) / "dist"
    if linked(output) or not output.resolve().is_relative_to(Path(project).resolve()):
        raise ValueError("Linked or escaping output directory")
    output.mkdir(exist_ok=True)
    targets = {ext: output / (name + ext) for ext in (".zip", ".manifest.json", ".sha256", ".verification.json")}
    if any(path.exists() or path.is_symlink() for path in targets.values()):
        raise ValueError("Output exists; choose a new package name")
    files, checks = collect_files(project, include_showcase)
    raw, manifest = archive_bytes(files, checks)
    result = verify_archive(raw, evaluate=True)
    content = {".zip": raw, ".manifest.json": manifest, ".sha256": (digest(raw) + "  " + name + ".zip\n").encode(),
               ".verification.json": encoded(result)}
    for extension, path in targets.items():
        with path.open("xb") as stream:
            stream.write(content[extension])
    return {"archive": targets[".zip"].relative_to(project).as_posix(), **result, **checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("build")
    create.add_argument("--name", required=True)
    create.add_argument("--include-showcase", action="store_true", help="Include a current verified showcase/dist build after the source freeze")
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--evaluate", action="store_true", help="Execute the included sensemaking.py authored regression with this Python environment")
    args = parser.parse_args()
    try:
        result = build(args.name, args.include_showcase) if args.command == "build" else verify_archive(read_archive(args.archive), args.evaluate)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        print("Package refused: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Create a deterministic transfer ZIP from a verified release, without networking.

Only manifest-listed wheels and five pinned handoff files are admitted. Existing
outputs are never replaced. Integrity checks are not cryptographic signatures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
HANDOFF_FILES = frozenset({"tools/live_parity.py", "tools/capacity_scenarios.py", "tools/benchmark_fixture.py", "tools/stress_exports.py",
                           "examples/capacity/scenarios.json"})
MAX_BUNDLE_BYTES = 128 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


def _digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def _read(path, maximum=2 * 1024 * 1024):
    with path.open("rb") as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("Bundle metadata exceeds its size budget")
    return content


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Release metadata contains duplicate keys")
        value[key] = item
    return value


def _path(root, name):
    relative = PurePosixPath(name)
    if (not name or relative.is_absolute() or relative.as_posix() != name
            or any(part in (".", "..") for part in relative.parts) or "\\" in name or ":" in name):
        raise ValueError("Unsafe bundle entry path")
    path = root.joinpath(*relative.parts)
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("Bundle inputs cannot be links")
    if not path.resolve().is_relative_to(root) or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Bundle input must be a regular file under its declared root")
    return path


def _entry(root, value):
    if (not isinstance(value, dict) or not isinstance(value.get("file"), str)
            or type(value.get("bytes")) is not int or not 0 < value["bytes"] <= MAX_BUNDLE_BYTES
            or not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"])):
        raise ValueError("Invalid bundle artifact metadata")
    path = _path(root, value["file"])
    if path.stat().st_size != value["bytes"]:
        raise ValueError("Bundle input size differs from verified manifest")
    return {"file": value["file"], "bytes": value["bytes"], "sha256": value["sha256"], "path": path}


def _inline(name, content):
    return {"file": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "content": content}


def _install(manifest):
    requirement = manifest["install_requirement"]
    target = manifest["target"]
    return (f"analytics311 {manifest['version']} verified offline wheel bundle\n\n"
            "Extract this archive to a writable folder. Python is not included.\n"
            f"Requires Python {manifest['requires_python']}. Native wheels must match this build target:\n"
            f"{target['python_implementation']} {target['python_version']}; {target['python_platform']}.\n"
            "Create a virtual environment: python -m venv .venv\n"
            "Windows interpreter: .venv/Scripts/python; Unix: .venv/bin/python\n"
            "Use that interpreter instead of python in the following commands:\n\n"
            f'python -m pip install --no-index --find-links . --find-links dependencies "{requirement}"\n'
            "python -m analytics311 describe\n"
            "python -m analytics311 plan-capacity --profile development --target-rows 1000\n"
            "python tools/capacity_scenarios.py --help\n"
            "python tools/live_parity.py --help\n\n"
            "Bounded generated-data measurement (10,000 rows; no Elastic scale inference):\n"
            "python tools/benchmark_fixture.py --data data/reference-10000.jsonl --output runs/reference-benchmark.json --records 10000 --repeats 3\n\n"
            "Local export concurrency and crash recovery (authored fixture, no engine-scale claim):\n"
            "python tools/stress_exports.py --output runs/export-stress.json\n\n"
            "Live parity requires a separately provisioned Elasticsearch and explicit fixture provisioning.\n"
            "Fixture checks and modeled capacity do not prove live-engine or million-record acceptance.\n"
            "release-manifest.json records the clean-install verification and wheel hashes.\n"
            "BUNDLE-MANIFEST.json covers every other archive entry. Hashes are not signatures.\n").encode("utf-8")


def bundle(release, output, *, source_root=ROOT):
    release, source_root = Path(release).resolve(), Path(source_root).resolve()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Bundle output already exists; choose a new filename")
    metadata = _read(_path(release, "release-manifest.json"))
    manifest = json.loads(metadata, object_pairs_hook=_object)
    if (not isinstance(manifest, dict) or manifest.get("name") != "analytics311"
            or not isinstance(manifest.get("version"), str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest["version"])
            or not isinstance(manifest.get("verification"), dict)
            or manifest.get("verification", {}).get("status") != "passed"):
        raise ValueError("Bundle requires a verified analytics311 release")
    extras = manifest.get("extras_bundled")
    if (not isinstance(extras, list) or any(not isinstance(extra, str) for extra in extras)
            or extras != sorted(set(extras)) or set(extras) - {"mcp", "geo"}):
        raise ValueError("Bundle extras must be the verified core/MCP/geo selection")
    requirement = "analytics311" + ("[" + ",".join(extras) + "]" if extras else "") + "==" + manifest["version"]
    if manifest.get("install_requirement") != requirement:
        raise ValueError("Install requirement differs from verified package identity")
    if (not isinstance(manifest["verification"].get("handoff"), dict)
            or manifest["verification"]["handoff"].get("status") != "passed"):
        raise ValueError("Transferred tools must pass the clean-install handoff smoke")
    stress = manifest["verification"]["handoff"].get("export_stress")
    if not isinstance(stress, dict) or stress.get("status") != "passed":
        raise ValueError("Transferred export stress tool must pass the clean-install smoke")
    for extra in extras:
        if manifest["verification"].get(extra + "_tested") is not True:
            raise ValueError("Selected optional adapter was not smoke-tested")
    target = manifest.get("target")
    if (not isinstance(target, dict) or any(not isinstance(target.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_.+ -]{1,80}", target[key])
            for key in ("python_implementation", "python_version", "python_platform"))
            or not isinstance(manifest.get("requires_python"), str) or not re.fullmatch(r"[><=0-9., ]{1,40}", manifest["requires_python"])):
        raise ValueError("Invalid target compatibility metadata")
    artifacts, handoff = manifest.get("artifacts"), manifest.get("handoff_files")
    if not isinstance(artifacts, list) or not 2 <= len(artifacts) <= 100 or not isinstance(handoff, list):
        raise ValueError("Release must include bounded wheel and handoff inventories")
    if len(handoff) != len(HANDOFF_FILES) or {item.get("file") for item in handoff if isinstance(item, dict)} != HANDOFF_FILES:
        raise ValueError("Release handoff inventory differs from the fixed allowlist")
    entries, project_wheels = [], 0
    for item in artifacts:
        entry = _entry(release, item)
        name = entry["file"]
        project_name = f"analytics311-{manifest['version']}-py3-none-any.whl"
        if name == project_name:
            project_wheels += 1
        elif not re.fullmatch(r"dependencies/[A-Za-z0-9_][A-Za-z0-9_.+-]{0,230}\.whl", name):
            raise ValueError("Release artifact is outside the wheel allowlist")
        entries.append(entry)
    if project_wheels != 1 or len({entry["file"].casefold() for entry in entries}) != len(entries):
        raise ValueError("Release needs one project wheel and no duplicate paths")
    entries.extend(_entry(source_root, item) for item in handoff)
    checksum = _read(_path(release, "SHA256SUMS"))
    expected = "".join(f"{item['sha256']}  {item['file']}\n" for item in artifacts).encode("utf-8")
    if checksum != expected:
        raise ValueError("SHA256SUMS differs from verified artifact inventory")
    entries.extend([_inline("release-manifest.json", metadata), _inline("SHA256SUMS", checksum),
                    _inline("INSTALL.txt", _install(manifest))])
    inventory = {entry["file"]: {key: entry[key] for key in ("bytes", "sha256")} for entry in sorted(entries, key=lambda item: item["file"])}
    receipt = {"schema_version": 1, "package_version": manifest["version"], "entries": inventory,
               "scope": "verified release wheels and hash-bound handoff tools; integrity is not a signature"}
    entries.append(_inline("BUNDLE-MANIFEST.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")))
    if sum(entry["bytes"] for entry in entries) > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds the 128 MiB input budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".analytics311-bundle-", suffix=".zip", dir=output.parent)
    os.close(handle)
    temporary = Path(temporary)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for entry in sorted(entries, key=lambda item: item["file"]):
                info = zipfile.ZipInfo(entry["file"], date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system, info.external_attr = 3, (stat.S_IFREG | 0o644) << 16
                digest, written = hashlib.sha256(), 0
                with archive.open(info, "w") as destination:
                    if "content" in entry:
                        destination.write(entry["content"])
                        digest.update(entry["content"])
                        written = len(entry["content"])
                    else:
                        with entry["path"].open("rb") as source:
                            while chunk := source.read(CHUNK_BYTES):
                                written += len(chunk)
                                if written > entry["bytes"]:
                                    raise ValueError("Bundle input grew during assembly")
                                destination.write(chunk)
                                digest.update(chunk)
                if written != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
                    raise ValueError("Bundle input changed since release verification")
        with zipfile.ZipFile(temporary) as archive:
            for entry in entries:
                with archive.open(entry["file"]) as stream:
                    if _digest(stream) != entry["sha256"]:
                        raise RuntimeError("Bundle verification failed")
        with temporary.open("rb") as stream:
            archive_hash = _digest(stream)
        # Exclusive hard-link publication is atomic and refuses a racing output.
        # Failure on a filesystem without hard links leaves no partial final ZIP.
        os.link(temporary, output)
        return {"file": output.name, "bytes": output.stat().st_size, "sha256": archive_hash,
                "entry_count": len(entries), "package_version": manifest["version"],
                "verification": "all entries re-read with CRC and exact SHA256; deterministic ZIP metadata",
                "entries_sha256": {entry["file"]: entry["sha256"] for entry in sorted(entries, key=lambda item: item["file"])}}
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = bundle(args.release, args.output)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"Bundle failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
